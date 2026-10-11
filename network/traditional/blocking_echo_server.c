#include <errno.h>
#include <netinet/in.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

/* Blocking accept/recv/send, one detached worker per connection. */
#define LIMIT 4096
static int clients[LIMIT];
static size_t active;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t drained = PTHREAD_COND_INITIALIZER;
static volatile sig_atomic_t stopping;
static volatile sig_atomic_t listener = -1;
static void stop(int sig) {
    (void)sig;
    stopping = 1;
    if (listener >= 0) { close(listener); listener = -1; }
}
static void *echo(void *arg) {
    size_t slot = (size_t)arg;
    int fd = clients[slot];
    char buf[2048];
    for (;;) {
        ssize_t n = recv(fd, buf, sizeof(buf), 0);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        ssize_t sent = 0;
        while (sent < n) {
            ssize_t k = send(fd, buf + sent, (size_t)(n - sent), MSG_NOSIGNAL);
            if (k < 0 && errno == EINTR) continue;
            if (k <= 0) goto done;
            sent += k;
        }
    }
done:
    pthread_mutex_lock(&lock);
    close(fd);
    clients[slot] = -1;
    --active;
    pthread_cond_signal(&drained);
    pthread_mutex_unlock(&lock);
    return NULL;
}
int main(int argc, char **argv) {
    char *end = NULL;
    long port = argc == 2 ? strtol(argv[1], &end, 10) : 0;
    if (!end || *end || port < 1 || port > 65535) return 1;
    for (size_t i = 0; i < LIMIT; ++i) clients[i] = -1;
    sigset_t signals;
    sigemptyset(&signals); sigaddset(&signals, SIGINT); sigaddset(&signals, SIGTERM);
    struct sigaction sa = {0}; sa.sa_handler = stop; sigemptyset(&sa.sa_mask);
    sigaction(SIGINT, &sa, NULL); sigaction(SIGTERM, &sa, NULL);
    int fd = socket(AF_INET, SOCK_STREAM, 0), yes = 1;
    if (fd < 0) { perror("socket"); return 1; }
    listener = fd;
    if (setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes))) return 1;
    struct sockaddr_in addr = { .sin_family = AF_INET, .sin_port = htons((unsigned short)port), .sin_addr.s_addr = INADDR_ANY };
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) || listen(fd, 512)) { perror("listen/bind"); return 1; }
    int failed = 0;
    while (!stopping) {
        int conn = accept(fd, NULL, NULL);
        if (conn < 0) {
            if (stopping) break;
            if (errno == EINTR || errno == ECONNABORTED) continue;
            perror("accept"); failed = 1; break;
        }
        pthread_mutex_lock(&lock);
        size_t slot;
        for (slot = 0; slot < LIMIT && clients[slot] != -1; ++slot) {}
        if (slot == LIMIT) { close(conn); failed = 1; pthread_mutex_unlock(&lock); break; }
        clients[slot] = conn; ++active;
        /* Deliver termination only to the accept thread. */
        pthread_sigmask(SIG_BLOCK, &signals, NULL);
        pthread_t worker;
        int rc = pthread_create(&worker, NULL, echo, (void *)slot);
        pthread_sigmask(SIG_UNBLOCK, &signals, NULL);
        if (rc) {
            fprintf(stderr, "pthread_create: %s\n", strerror(rc));
            close(conn); clients[slot] = -1; --active; failed = 1;
        } else pthread_detach(worker);
        pthread_mutex_unlock(&lock);
        if (failed) break;
    }
    if (listener >= 0) close(listener);
    pthread_mutex_lock(&lock);
    for (size_t i = 0; i < LIMIT; ++i) if (clients[i] >= 0) shutdown(clients[i], SHUT_RDWR);
    while (active) pthread_cond_wait(&drained, &lock);
    pthread_mutex_unlock(&lock);
    return failed;
}
