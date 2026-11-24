#include "review_ops.h"

#include <stdio.h>
#include <string.h>

#include "lwip/netdb.h"
#include "lwip/sockets.h"
#include "review_contract.h"

#define LITERAL_SIZE(text) (sizeof(text) - 1)

static int open_socket(const char *address, int port, int type)
{
    struct sockaddr_in endpoint = {
        .sin_family = AF_INET,
        .sin_port = htons(port),
        .sin_addr.s_addr = inet_addr(address),
    };
    int fd = socket(AF_INET, type, 0);
    if (fd < 0) {
        return -1;
    }
    struct timeval timeout = {.tv_sec = REVIEW_OP_TIMEOUT_S, .tv_usec = 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
    if (connect(fd, (const struct sockaddr *)&endpoint, sizeof(endpoint)) != 0) {
        close(fd);
        return -1;
    }
    return fd;
}

static bool send_all(int fd, const void *data, size_t size)
{
    const char *cursor = data;
    while (size) {
        int sent = send(fd, cursor, size, 0);
        if (sent <= 0) {
            return false;
        }
        cursor += sent;
        size -= sent;
    }
    return true;
}

/* Read exactly `size` bytes; the fixture need not close the stream. */
static bool recv_exact(int fd, void *data, size_t size)
{
    char *cursor = data;
    while (size) {
        int received = recv(fd, cursor, size, 0);
        if (received <= 0) {
            return false;
        }
        cursor += received;
        size -= received;
    }
    return true;
}

bool review_dns_resolves(const char *name, char *address, size_t address_size)
{
    struct addrinfo hints = {.ai_family = AF_INET, .ai_socktype = SOCK_STREAM};
    struct addrinfo *result = NULL;
    bool ok = getaddrinfo(name, NULL, &hints, &result) == 0 && result != NULL;
    address[0] = '\0';
    if (ok) {
        const struct sockaddr_in *ipv4 = (const struct sockaddr_in *)result->ai_addr;
        inet_ntoa_r(ipv4->sin_addr, address, address_size);
        ok = strcmp(address, REVIEW_GATEWAY) == 0;
    }
    if (result) {
        freeaddrinfo(result);
    }
    printf("REVIEW_CTRL DNS_A ok=%u name=%s address=%s\n", ok, name, address[0] ? address : "-");
    return ok;
}

bool review_dns_absent(const char *name)
{
    struct addrinfo hints = {.ai_family = AF_INET, .ai_socktype = SOCK_STREAM};
    struct addrinfo *result = NULL;
    int status = getaddrinfo(name, NULL, &hints, &result);
    if (result) {
        freeaddrinfo(result);
    }
    bool ok = status != 0;
    printf("REVIEW_CTRL DNS_NXDOMAIN ok=%u name=%s\n", ok, name);
    return ok;
}

/*
 * Parse one HTTP/1.x response by Content-Length. Returns true only for
 * status 200 with exactly `expected` as the body.
 */
static bool http_exchange(const char *address, const char *request, size_t request_size,
                          const char *expected, size_t expected_size, unsigned *status_out)
{
    *status_out = 0;
    int fd = open_socket(address, REVIEW_HTTP_PORT, SOCK_STREAM);
    if (fd < 0) {
        return false;
    }
    char response[768] = {0};
    size_t used = 0;
    bool ok = send_all(fd, request, request_size);
    bool exact = false;
    while (ok && used < sizeof(response) - 1) {
        int size = recv(fd, response + used, sizeof(response) - 1 - used, 0);
        if (size <= 0) {
            break;
        }
        used += size;
        response[used] = '\0';
        char *header_end = strstr(response, "\r\n\r\n");
        if (!header_end) {
            continue;
        }
        unsigned status = 0;
        sscanf(response, "HTTP/1.%*c %u", &status);
        *status_out = status;
        const char *length_field = strstr(response, "\r\nContent-Length: ");
        if (!length_field || length_field > header_end) {
            break;
        }
        unsigned length = 0;
        sscanf(length_field + LITERAL_SIZE("\r\nContent-Length: "), "%u", &length);
        size_t body_offset = (size_t)(header_end + 4 - response);
        if (used >= body_offset + length) {
            exact = status == 200 && length == expected_size
                && memcmp(response + body_offset, expected, expected_size) == 0;
            break;
        }
    }
    close(fd);
    return ok && exact;
}

bool review_http_get(const char *address)
{
    static const char request[] =
        "GET " REVIEW_HTTP_GET_PATH " HTTP/1.1\r\nHost: " REVIEW_DNS_NAME "\r\nConnection: close\r\n\r\n";
    unsigned status = 0;
    bool ok = http_exchange(address, request, LITERAL_SIZE(request), REVIEW_HTTP_GET_BODY,
                            LITERAL_SIZE(REVIEW_HTTP_GET_BODY), &status);
    printf("REVIEW_CTRL HTTP_GET ok=%u status=%u path=%s\n", ok, status, REVIEW_HTTP_GET_PATH);
    return ok;
}

bool review_http_post(const char *address)
{
    char request[256];
    int size = snprintf(request, sizeof(request),
                        "POST %s HTTP/1.1\r\nHost: %s\r\nContent-Type: application/json\r\n"
                        "Content-Length: %u\r\nConnection: close\r\n\r\n%s",
                        REVIEW_HTTP_POST_PATH, REVIEW_DNS_NAME,
                        (unsigned)LITERAL_SIZE(REVIEW_HTTP_POST_BODY), REVIEW_HTTP_POST_BODY);
    unsigned status = 0;
    bool ok = size > 0 && size < (int)sizeof(request)
        && http_exchange(address, request, (size_t)size, REVIEW_HTTP_POST_REPLY,
                         LITERAL_SIZE(REVIEW_HTTP_POST_REPLY), &status);
    printf("REVIEW_CTRL HTTP_POST ok=%u status=%u path=%s\n", ok, status, REVIEW_HTTP_POST_PATH);
    return ok;
}

bool review_tcp_exchange(const char *address)
{
    static const char request[] = REVIEW_TCP_REQUEST;
    static const char expected[] = REVIEW_TCP_REPLY;
    char reply[sizeof(expected)] = {0};
    int fd = open_socket(address, REVIEW_TCP_PORT, SOCK_STREAM);
    bool ok = fd >= 0 && send_all(fd, request, LITERAL_SIZE(request))
        && recv_exact(fd, reply, LITERAL_SIZE(expected))
        && memcmp(reply, expected, LITERAL_SIZE(expected)) == 0;
    if (fd >= 0) {
        close(fd);
    }
    printf("REVIEW_CTRL TCP ok=%u port=%u\n", ok, REVIEW_TCP_PORT);
    return ok;
}

bool review_udp_exchange(const char *address)
{
    static const char request[] = REVIEW_UDP_REQUEST;
    static const char expected[] = REVIEW_UDP_REPLY;
    char reply[64];
    int fd = open_socket(address, REVIEW_UDP_PORT, SOCK_DGRAM);
    int count = -1;
    if (fd >= 0 && send(fd, request, LITERAL_SIZE(request), 0) == (int)LITERAL_SIZE(request)) {
        count = recv(fd, reply, sizeof(reply), 0);
    }
    if (fd >= 0) {
        close(fd);
    }
    bool ok = count == (int)LITERAL_SIZE(expected) && memcmp(reply, expected, LITERAL_SIZE(expected)) == 0;
    printf("REVIEW_CTRL UDP ok=%u port=%u\n", ok, REVIEW_UDP_PORT);
    return ok;
}

/* MQTT 3.1.1 CONNECT (clean session), CONNACK, QoS0 PUBLISH, DISCONNECT. */
bool review_mqtt_publish(const char *address)
{
    static const char client[] = REVIEW_MQTT_CLIENT_ID;
    static const char topic[] = REVIEW_MQTT_TOPIC;
    static const char payload[] = REVIEW_MQTT_PAYLOAD;
    unsigned char packet[128];
    size_t n = 0;
    size_t variable = 10 + 2 + LITERAL_SIZE(client);
    packet[n++] = 0x10;
    packet[n++] = (unsigned char)variable;
    static const unsigned char header[] = {0, 4, 'M', 'Q', 'T', 'T', 4, 0x02, 0, 60};
    memcpy(packet + n, header, sizeof(header));
    n += sizeof(header);
    packet[n++] = 0;
    packet[n++] = (unsigned char)LITERAL_SIZE(client);
    memcpy(packet + n, client, LITERAL_SIZE(client));
    n += LITERAL_SIZE(client);

    unsigned char connack[4] = {0};
    int fd = open_socket(address, REVIEW_MQTT_PORT, SOCK_STREAM);
    bool connected = fd >= 0 && send_all(fd, packet, n) && recv_exact(fd, connack, sizeof(connack))
        && connack[0] == 0x20 && connack[1] == 2 && connack[3] == 0;
    bool published = false;
    if (connected) {
        n = 0;
        packet[n++] = 0x30;
        packet[n++] = (unsigned char)(2 + LITERAL_SIZE(topic) + LITERAL_SIZE(payload));
        packet[n++] = 0;
        packet[n++] = (unsigned char)LITERAL_SIZE(topic);
        memcpy(packet + n, topic, LITERAL_SIZE(topic));
        n += LITERAL_SIZE(topic);
        memcpy(packet + n, payload, LITERAL_SIZE(payload));
        n += LITERAL_SIZE(payload);
        static const unsigned char disconnect[] = {0xe0, 0};
        published = send_all(fd, packet, n) && send_all(fd, disconnect, sizeof(disconnect));
    }
    if (fd >= 0) {
        close(fd);
    }
    printf("REVIEW_CTRL MQTT ok=%u connack=%u topic=%s\n", connected && published, connected, topic);
    return connected && published;
}
