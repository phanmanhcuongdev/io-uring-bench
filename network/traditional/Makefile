CFLAGS ?= -Wall -Wextra -Werror -O2 -D_GNU_SOURCE
all: blocking_echo_server
blocking_echo_server: blocking_echo_server.c
	$(CC) $(CFLAGS) -pthread $< -o $@
clean:
	rm -f blocking_echo_server
.PHONY: all clean
