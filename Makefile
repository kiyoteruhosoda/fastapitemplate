# ================================
# fastapitemplate Makefile（ビルドの実体は scripts/build.sh）
# ================================

.PHONY: build clean

# クロスビルドしたいときだけ指定する（例: make build PLATFORM=linux/amd64）。
# 無指定なら実行ホストのネイティブアーキテクチャでビルドする。
PLATFORM ?=

build:
	PLATFORM=$(PLATFORM) ./scripts/build.sh

clean:
	rm -rf dist
