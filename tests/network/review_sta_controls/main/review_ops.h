#pragma once

#include <stdbool.h>
#include <stddef.h>

/* Each operation prints one `REVIEW_CTRL <NAME> ok=<0|1> ...` line. */
bool review_dns_resolves(const char *name, char *address, size_t address_size);
bool review_dns_absent(const char *name);
bool review_http_get(const char *address);
bool review_http_post(const char *address);
bool review_tcp_exchange(const char *address);
bool review_udp_exchange(const char *address);
bool review_mqtt_publish(const char *address);
