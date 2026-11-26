FROM scratch
ARG SERVICE
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.source="https://github.com/microservices-demo/${SERVICE}" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      thesis.shyn.execution-mode="native-arm64-experimental" \
      thesis.shyn.compiler="go1.23.12"
COPY app /app
COPY LICENSE /LICENSE
COPY licenses/ /licenses/
COPY images/ /images/
USER 10001:10001
EXPOSE 80
ENTRYPOINT ["/app"]
CMD ["-port=80"]
