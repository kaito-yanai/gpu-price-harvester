# 1. ベースOSとPython環境
FROM python:3.11-slim

# 2. 作業ディレクトリ
WORKDIR /app

# 3. 必要なツールとGoogle Chromeの公式リポジトリを追加（apt-keyを使わない新方式）
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    unzip \
    gnupg \
    jq \
    --no-install-recommends \
    # --- ここからがChromeリポジトリの新しい登録方法 ---
    # 1. Googleの署名キーをダウンロードし、キーリングディレクトリに保存
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
    # 2. Googleのリポジトリ情報をリストに追加（どのキーで署名されているかを明記）
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    # --- ここまで ---
    # リポジトリ情報を更新
    && apt-get update \
    # Google Chromeをインストール
    && apt-get install -y \
    google-chrome-stable \
    --no-install-recommends \
    # 後片付け
    && rm -rf /var/lib/apt/lists/*

# 4. chromedriverの確実なインストール処理
RUN set -ex && \
    CHROME_BUILD_VERSION=$(google-chrome --version | cut -d ' ' -f 3 | cut -d '.' -f 1-3) && \
    DRIVER_VERSION=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/latest-patch-versions-per-build.json" | jq -r ".builds[\"${CHROME_BUILD_VERSION}\"].version") && \
    curl -s -L -o /tmp/chromedriver.zip "https://edgedl.me.gvt1.com/edgedl/chrome/chrome-for-testing/${DRIVER_VERSION}/linux64/chromedriver-linux64.zip" && \
    unzip /tmp/chromedriver.zip -d /tmp && \
    mv /tmp/chromedriver-linux64/chromedriver /usr/bin/chromedriver && \
    ls -l /usr/bin/chromedriver && \
    chmod +x /usr/bin/chromedriver && \
    rm -rf /tmp/chromedriver.zip /tmp/chromedriver-linux64

# 5. Pythonライブラリのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. プロジェクトの全ファイルをコピー
COPY . .

# 7. Cloud Runの起動コマンド
CMD ["functions-framework", "--target=screenshot_entry_point", "--port=8080"]