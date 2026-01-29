# WebCam Share

ネットワーク経由でWebカメラを共有し、仮想カメラとして利用できるアプリケーションです。

## ダウンロード

👉 **[最新版をダウンロード](https://github.com/tatsu020/WebCamShare/releases/latest)**

ダウンロードしたzipファイルを解凍し、WebCamShare.exeファイルを実行してください。

> ⚠️ **受信側（Receiver）の準備**  
> [OBS Studio](https://obsproject.com/) をインストールしてください（仮想カメラドライバが自動で登録されます）。

## 機能

- **Sender Mode**: Webカメラの映像をMJPEGストリームとして配信
- **Receiver Mode**: 配信された映像を受信し、仮想カメラデバイスとして出力

## 使い方

### Sender Mode（配信側）

1. メイン画面で「Sender Mode」を選択
2. 使用するカメラを選択
3. 「Start Streaming」をクリック
4. 同一ネットワーク内のReceiverからアクセス可能になります

### Receiver Mode（受信側）

1. メイン画面で「Receiver Mode」を選択
2. ネットワーク上のSenderを自動検出、または手動でIPを入力
3. 「Connect」をクリックして接続
4. 受信映像が「OBS Virtual Camera」として出力されます
5. Zoom、Teams等のアプリで「OBS Virtual Camera」を選択して使用

## 開発者向け

### 必要要件

- [uv](https://docs.astral.sh/uv/)
- Python 3.9+
- Windows 10/11
- [OBS Studio](https://obsproject.com/) （仮想カメラ機能を使用するため）

### 起動

```bash
run.bat
```

これで依存関係の同期とアプリの起動が自動で行われます。

#### 手動で実行する場合

```bash
uv sync
uv run main.py
```

## ネットワーク

- ストリーミングポート: 8000 (HTTP/MJPEG)
- ディスカバリーポート: 8001 (UDP Broadcast)

## ライセンス

GPL-2.0 License
