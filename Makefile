# ================================
# fastapitemplate Makefile (build + docker-save tar + deploy assets)
# ================================

.PHONY: build build-db dist-assets clean

IMAGE_NAME    = fastapitemplate:latest
DB_IMAGE_NAME = fastapitemplate-db:latest
DIST_DIR      = dist
OUTPUT_TAR    = $(DIST_DIR)/image.tar
DB_OUTPUT_TAR = $(DIST_DIR)/image-db.tar
PLATFORM      = linux/amd64

# Git情報（make 実行時に取得）
COMMIT_HASH      := $(shell git rev-parse --short HEAD)
COMMIT_HASH_FULL := $(shell git rev-parse HEAD)
BRANCH           := $(shell git rev-parse --abbrev-ref HEAD)
COMMIT_DATE      := $(shell git log -1 --format=%ci)
BUILD_DATE       := $(shell date -Iseconds)

# デプロイ用スクリプトを dist/ へ配置する（配置先サーバーの <app>/<stg|prod>/ へは
# dist/ の中身をそのまま持っていく）。
dist-assets:
	@mkdir -p $(DIST_DIR)/scripts
	install -m 755 scripts/deploy.sh $(DIST_DIR)/scripts/deploy.sh
	@echo "Deploy assets placed under $(DIST_DIR)/"

build:
	@mkdir -p $(DIST_DIR)
	docker buildx build \
	  --platform $(PLATFORM) \
	  --build-arg COMMIT_HASH=$(COMMIT_HASH) \
	  --build-arg COMMIT_HASH_FULL=$(COMMIT_HASH_FULL) \
	  --build-arg BRANCH=$(BRANCH) \
	  --build-arg COMMIT_DATE="$(COMMIT_DATE)" \
	  --build-arg BUILD_DATE="$(BUILD_DATE)" \
	  -t $(IMAGE_NAME) . \
	  --load
	docker save $(IMAGE_NAME) -o $(OUTPUT_TAR)
	chmod 644 $(OUTPUT_TAR)
	$(MAKE) dist-assets
	@echo "Build complete: $(OUTPUT_TAR)"

build-db:
	@mkdir -p $(DIST_DIR)
	docker buildx build \
	  --platform $(PLATFORM) \
	  -t $(DB_IMAGE_NAME) ./db \
	  --load
	docker save $(DB_IMAGE_NAME) -o $(DB_OUTPUT_TAR)
	chmod 644 $(DB_OUTPUT_TAR)
	$(MAKE) dist-assets
	@echo "Build complete: $(DB_OUTPUT_TAR)"

clean:
	rm -rf $(DIST_DIR)
