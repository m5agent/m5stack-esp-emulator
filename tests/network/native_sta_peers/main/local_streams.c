#include "local_streams.h"

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <unistd.h>

#include "esp_timer.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"

#define FIXTURE_IP "10.0.2.2"
#define POST_PORT 18193
#define TCP_PORT 19193
#define STREAM_BUDGET_US (5 * 1000 * 1000)
#define HTTP_MAX_HEADER 512

static const uint8_t post_request[] = {0x4d, 0x35, 0x50, 0x4f, 0x53, 0x54, 0, 0x7f, 0xff, 0x11};
static const uint8_t post_reply[] = {0x41, 0x43, 0x4b, 0x2d, 0x50, 0x4f, 0x53, 0x54, 0, 0x7f, 0xff, 0x11};
static const uint8_t tcp_request[] = {0x4d, 0x35, 0x54, 0x43, 0x50, 0, 0x80, 0xfe, 0x22};
static const uint8_t tcp_reply[] = {0x41, 0x43, 0x4b, 0x2d, 0x54, 0x43, 0x50, 0, 0x80, 0xfe, 0x22};

typedef struct {
    int fd;
    int64_t deadline_us;
} fixture_stream_t;

static bool wait_socket(const fixture_stream_t *stream, bool write_ready)
{
    int64_t remaining = stream->deadline_us - esp_timer_get_time();
    if (remaining <= 0) {
        return false;
    }
    struct timeval timeout = {.tv_sec = remaining / 1000000, .tv_usec = remaining % 1000000};
    fd_set ready;
    FD_ZERO(&ready);
    FD_SET(stream->fd, &ready);
    return select(stream->fd + 1, write_ready ? NULL : &ready,
                  write_ready ? &ready : NULL, NULL, &timeout) == 1;
}

static fixture_stream_t connect_fixture(uint16_t port)
{
    fixture_stream_t stream = {
        .fd = socket(AF_INET, SOCK_STREAM, 0),
        .deadline_us = esp_timer_get_time() + STREAM_BUDGET_US,
    };
    if (stream.fd < 0) {
        return stream;
    }
    struct sockaddr_in peer = {
        .sin_family = AF_INET,
        .sin_port = htons(port),
        .sin_addr.s_addr = inet_addr(FIXTURE_IP),
    };
    if (fcntl(stream.fd, F_SETFL, O_NONBLOCK) == 0) {
        if (connect(stream.fd, (const struct sockaddr *)&peer, sizeof(peer)) == 0) {
            return stream;
        }
        if (errno == EINPROGRESS && wait_socket(&stream, true)) {
            int error = 0;
            socklen_t size = sizeof(error);
            if (getsockopt(stream.fd, SOL_SOCKET, SO_ERROR, &error, &size) == 0 && error == 0) {
                return stream;
            }
        }
    }
    close(stream.fd);
    stream.fd = -1;
    return stream;
}

static bool send_all(const fixture_stream_t *stream, const void *data, size_t size)
{
    const uint8_t *cursor = data;
    while (size && wait_socket(stream, true)) {
        ssize_t sent = send(stream->fd, cursor, size, 0);
        if (sent < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            continue;
        }
        if (sent <= 0) {
            return false;
        }
        cursor += sent;
        size -= sent;
    }
    return size == 0;
}

static ssize_t read_some(const fixture_stream_t *stream, void *data, size_t size)
{
    while (wait_socket(stream, false)) {
        ssize_t received = recv(stream->fd, data, size, 0);
        if (received >= 0 || (errno != EAGAIN && errno != EWOULDBLOCK)) {
            return received;
        }
    }
    return -1;
}

static bool read_exact(const fixture_stream_t *stream, void *data, size_t size)
{
    uint8_t *cursor = data;
    while (size) {
        ssize_t received = read_some(stream, cursor, size);
        if (received <= 0) {
            return false;
        }
        cursor += received;
        size -= received;
    }
    return true;
}

static bool post_header_matches(const char *header, const char *end)
{
    if (strncmp(header, "HTTP/1.0 200 ", 13) && strncmp(header, "HTTP/1.1 200 ", 13)) {
        return false;
    }
    const char *line = strstr(header, "\r\n") + 2;
    const char length_header[] = "Content-Length:";
    char expected_length[12];
    int length_size = snprintf(expected_length, sizeof(expected_length), "%zu", sizeof(post_reply));
    bool size_matches = false;
    while (line < end) {
        const char *next = strstr(line, "\r\n");
        if (strncasecmp(line, "Transfer-Encoding:", 18) == 0) {
            return false;
        }
        if (strncasecmp(line, length_header, sizeof(length_header) - 1) == 0) {
            const char *value = line + sizeof(length_header) - 1;
            while (value < next && (*value == ' ' || *value == '\t')) {
                value++;
            }
            if (size_matches || next - value != length_size || memcmp(value, expected_length, length_size)) {
                return false;
            }
            size_matches = true;
        }
        line = next + 2;
    }
    return size_matches;
}

static bool read_post_response(const fixture_stream_t *stream)
{
    char reply[HTTP_MAX_HEADER + sizeof(post_reply) + 1];
    size_t used = 0;
    while (used < HTTP_MAX_HEADER) {
        ssize_t received = read_some(stream, reply + used, sizeof(reply) - used - 1);
        if (received <= 0) {
            return false;
        }
        used += received;
        reply[used] = '\0';
        char *end = strstr(reply, "\r\n\r\n");
        if (end == NULL) {
            continue;
        }
        char *body = end + 4;
        size_t header_size = body - reply;
        size_t have = used - header_size;
        return header_size <= HTTP_MAX_HEADER && have <= sizeof(post_reply)
            && post_header_matches(reply, end)
            && read_exact(stream, body + have, sizeof(post_reply) - have)
            && memcmp(body, post_reply, sizeof(post_reply)) == 0;
    }
    return false;
}

bool native_sta_post_matches(void)
{
    fixture_stream_t stream = connect_fixture(POST_PORT);
    if (stream.fd < 0) {
        return false;
    }
    char header[160];
    int size = snprintf(header, sizeof(header),
                        "POST /native-sta-post HTTP/1.0\r\nHost: post.native-sta.test\r\n"
                        "Content-Type: application/octet-stream\r\nContent-Length: %zu\r\n\r\n",
                        sizeof(post_request));
    bool matched = size > 0 && (size_t)size < sizeof(header)
        && send_all(&stream, header, size)
        && send_all(&stream, post_request, sizeof(post_request))
        && read_post_response(&stream);
    close(stream.fd);
    return matched;
}

bool native_sta_tcp_matches(void)
{
    fixture_stream_t stream = connect_fixture(TCP_PORT);
    if (stream.fd < 0) {
        return false;
    }
    uint8_t request_size[2] = {sizeof(tcp_request) >> 8, sizeof(tcp_request) & 0xff};
    uint8_t reply_size[2];
    uint8_t reply[sizeof(tcp_reply)];
    bool matched = send_all(&stream, request_size, sizeof(request_size))
        && send_all(&stream, tcp_request, sizeof(tcp_request))
        && read_exact(&stream, reply_size, sizeof(reply_size))
        && ((size_t)reply_size[0] << 8 | reply_size[1]) == sizeof(reply)
        && read_exact(&stream, reply, sizeof(reply))
        && memcmp(reply, tcp_reply, sizeof(tcp_reply)) == 0;
    close(stream.fd);
    return matched;
}
