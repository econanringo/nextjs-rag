# Next.js 公式ドキュメント RAG（next-devtools-mcp）

[公式の `next-devtools-mcp`](https://www.npmjs.com/package/next-devtools-mcp) を経由して Next.js の公式ドキュメントを取得し、その内容だけを根拠に質問に答える Python の CLI です。MCP の `nextjs_docs` と `nextjs-docs://llms-index` を使うため、検索対象は常に公式が配布するインデックス／本文に沿います。

## 前提条件

- **Python 3.10+**（プロジェクトでは 3.14 付近で動作確認）
- **Node.js と `npx`**（MCP サーバーを `npx -y next-devtools-mcp` で起動するため）
- **OpenAI 互換の Chat API** に渡せる API キー（例: [NVIDIA Integrate API](https://build.nvidia.com/)）

## セットアップ

```bash
cd /path/to/rag
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

環境変数用に `.env` を用意します。

```bash
cp .env.example .env
# .env を編集して API キーなどを設定
```

## 環境変数

| 変数 | 必須 | 説明 |
|------|------|------|
| `NVIDIA_API_KEY` または `OPENAI_API_KEY` | はい | Chat API 用のキー |
| `NVIDIA_OPENAI_BASE_URL` または `OPENAI_BASE_URL` | 推奨 | 互換 API のベース URL（NVIDIA 利用時は `.env.example` の URL を参照） |
| `CHAT_MODEL` | いいえ | 既定: `nvidia/nemotron-3-nano-30b-a3b` |
| `CHAT_TEMPERATURE` | いいえ | 既定: `0.2` |
| `CHAT_EXTRA_BODY` | いいえ | `extra_body` に渡す JSON（例: Nemotron の推論オプション）。1 行の JSON 文字列 |
| `CHAT_STREAM` | いいえ | `1` / `true` / `yes` / `on` でストリーミング（既定）。`0` など falsy で常に **非ストリーミング** のみ送信 |
| `CHAT_STREAM_FALLBACK` | いいえ | 既定オン。ストリームを最後まで読んでも表示用テキストが一度も出ないとき、同じ入力で **非ストリーミングを 1 回** 試す |
| `CHAT_MAX_TOKENS` | いいえ | 設定時のみ、`max_tokens` としてリクエストに付与 |
| `CHAT_STREAM_INCLUDE_USAGE` | いいえ | オン時、ストリーミング要求に `stream_options: {"include_usage": true}` を付与（使用量を最終チャンクで受け取る用途） |
| `CHAT_HTTP_TIMEOUT_SECONDS` | いいえ | 読み取り込みを含む HTTP タイムアウト（秒）。既定: `600` |
| `OPENAI_TIMEOUT` または `HTTP_TIMEOUT` | いいえ | 上記と同目的。評価は **`OPENAI_TIMEOUT` → `HTTP_TIMEOUT` → `CHAT_HTTP_TIMEOUT_SECONDS`** の先勝ち |
| `CHAT_HTTP_CONNECT_SECONDS` | いいえ | 接続確立までのタイムアウト（秒）。既定: `30`（遅い TLS でも切れにくくするため） |
| `NEXTJS_MCP_COMMAND` | いいえ | MCP 起動コマンド（シェルと同様に空白区切り）。既定: `npx -y next-devtools-mcp` |
| `RAG_TOP_K` | いいえ | `--top-k` の既定値（ページ取得数）。既定: `4` |

### Chat API（モデル差の吸収）

OpenAI の Chat Completions 互換エンドポイントを前提にしています。プロバイダやモデルによって次のような差があります。

- **ストリーム本文の欠落** … ゲートウェイ側でストリーミングの `delta` に本文が載らない場合がある → 既定では `CHAT_STREAM_FALLBACK` により **非ストリームで再試行**。
- **推論フィールドの名称** … `reasoning_content` 以外に `reasoning` / `thinking` / `thought` などで返す API がある → これらをまとめて標準出力に流します（通常は推論が先に、続けて `content`）。
- **`content` の形** … 文字列だけでなく、`type: "text"` のブロックの配列で返す実装に対応します。

大規模モデル（例: `nvidia/nemotron-3-super-120b-a12b`）は **最初のトークンまで数十秒〜数分かかる**ことがあります。ログに path が出たあと無言に見える場合は、しばらく待つか、`CHAT_HTTP_TIMEOUT_SECONDS` をさらに延ばしてください。ストリームが不安定なら `CHAT_STREAM=0` で非ストリーム固定にすると確実です。

## 使い方

基本的な実行:

```bash
python main.py "App Router で Server Actions を使うには？"
```

取得するドキュメントページ数を増やす:

```bash
python main.py --top-k 5 "キャッシュの revalidate について"
```

ヘルプ:

```bash
python main.py --help
```

標準出力へ回答が **できる限りストリーミング** で表示されます（非対応や空ストリームのときは自動でもう一度非ストリームで試します。無効化したい場合は `CHAT_STREAM_FALLBACK=0`）。処理の冒頭で「取得したドキュメント path: …」と、今回参照した `/docs/...` の一覧が出ます。

## 動作の流れ（概要）

1. 子プロセスで `next-devtools-mcp` を起動し、MCP セッションを確立する。
2. リソース `nextjs-docs://llms-index` で公式インデックス（`llms.txt` 相当）を読む。
3. 質問文とインデックス行の単語重なりで、関連しそうなドキュメント path を最大 `top_k` 件選ぶ。
4. 各 path に対してツール `nextjs_docs` で本文を取得する。
5. 取得本文をコンテキストとして、設定した Chat モデルに送り、回答を生成する。

LLM は可能なら **ストリーミング** で逐次表示し、(5) が本文ゼロで終わった場合のみ **同一プロンプトを非ストリーミングで再実行**します（`CHAT_STREAM_FALLBACK` がオンで、`CHAT_STREAM` がオンなとき）。

インデックス説明が英語中心のため、日本語のみの短い質問だと取得 path が外れやすい場合があります。そのときは **`--top-k` を大きくする**か、ドキュメントで使われている用語（Server Actions、Route Handler など）を混ぜてみてください。

## MCP ツールについて（よくある誤解）

この README の対象は **公式サイトのドキュメントを読む**経路です。

- **`nextjs_docs` / `llms-index`** … nextjs.org の公式ドキュメントに基づいて答える（本プロジェクトが利用）。
- **`nextjs_index` / `nextjs_call`** … ローカルで動いている **Next.js 16 以降の開発サーバー**の MCP（`/_next/mcp`）に接続し、コンパイルエラーやルート情報など**実行中アプリの状態**を調べる用途。

アプリのランタイム診断まで Python から行いたい場合は、別途 dev サーバーを起動したうえで、そのツール群を呼び出す実装が必要になります。

## トラブルシューティング

- **`npx` が見つからない** … Node.js をインストールし、`NEXTJS_MCP_COMMAND` でフルパスの `npx` を指定するか、`PATH` を通してください。
- **`next-devtools-mcp` の起動に失敗する** … ネットワークで npm レジストリに届くか、`npx -y next-devtools-mcp` を手動で実行できるか確認してください。
- **関連ドキュメントが取得できない** … 質問を変える、`--top-k` を増やす、英語キーワードを足す。
- **API エラー** … `.env` のベース URL・モデル名・キーが、そのプロバイダの OpenAI 互換仕様と一致しているか確認してください。
- **回答がずっと出ない（path のあとで止まる）** … 大モデルは初回トークンが遅いことがあるため待機する。長すぎる場合は `CHAT_HTTP_TIMEOUT_SECONDS` を延ばす。ストリームが空のまま終わる API では `CHAT_STREAM_FALLBACK`（既定オン）で非ストリームに切り替わるはずなので、それでもダメなら `CHAT_STREAM=0` や `CHAT_MAX_TOKENS` / `CHAT_EXTRA_BODY` でプロバイダ必須パラメータを渡す。

## ライセンス

リポジトリ側のライセンスに従ってください。`next-devtools-mcp` 本体は npm パッケージのライセンス（MIT）が適用されます。
