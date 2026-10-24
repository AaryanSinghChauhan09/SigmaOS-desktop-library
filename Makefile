.PHONY: build test install clean
build:
	cargo build --release
test:
	cargo test --release
install:
	install -Dm755 target/release/* $(DESTDIR)/usr/bin/ 2>/dev/null || true
clean:
	cargo clean
