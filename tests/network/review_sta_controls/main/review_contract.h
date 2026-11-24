/*
 * Fixed review-sta control contract. The Device Service fixture must serve
 * exactly these endpoints; change both sides together.
 */
#pragma once

#define REVIEW_SSID "M5-REVIEW"
#define REVIEW_PASSPHRASE "review-pass-v1"
#define REVIEW_WRONG_PASSPHRASE "review-wrong-v1"
#define REVIEW_MAX_CONNECT_ATTEMPTS 3
#define REVIEW_LEASE_WAIT_MS 30000
#define REVIEW_OP_TIMEOUT_S 5

#define REVIEW_GATEWAY "10.0.2.2"
#define REVIEW_DNS_NAME "review.test"
#define REVIEW_DNS_ABSENT "absent.test"

#define REVIEW_HTTP_PORT 80
#define REVIEW_HTTP_GET_PATH "/review/status"
#define REVIEW_HTTP_GET_BODY "REVIEW_OK\n"
#define REVIEW_HTTP_POST_PATH "/review/config"
#define REVIEW_HTTP_POST_BODY "{\"probe\":1}"
#define REVIEW_HTTP_POST_REPLY "{\"ok\":true}"

#define REVIEW_TCP_PORT 19193
#define REVIEW_TCP_REQUEST "M5TCP\x00\x01"
#define REVIEW_TCP_REPLY "ACK-M5TCP\x00\x01"

#define REVIEW_UDP_PORT 19090
#define REVIEW_UDP_REQUEST "M5UDP\x00\x02"
#define REVIEW_UDP_REPLY "ACK-M5UDP\x00\x02"

#define REVIEW_MQTT_PORT 1883
#define REVIEW_MQTT_CLIENT_ID "review-ctrl"
#define REVIEW_MQTT_TOPIC "review/ctrl"
#define REVIEW_MQTT_PAYLOAD "hello"
