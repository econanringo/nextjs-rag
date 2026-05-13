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
| `NEXTJS_MCP_COMMAND` | いいえ | MCP 起動コマンド（シェルと同様に空白区切り）。既定: `npx -y next-devtools-mcp` |
| `RAG_TOP_K` | いいえ | `--top-k` の既定値（ページ取得数）。既定: `4` |

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

標準出力へ回答がストリーム表示されます。処理の冒頭で「取得したドキュメント path: …」と、今回参照した `/docs/...` の一覧が出ます。

## 動作の流れ（概要）

1. 子プロセスで `next-devtools-mcp` を起動し、MCP セッションを確立する。
2. リソース `nextjs-docs://llms-index` で公式インデックス（`llms.txt` 相当）を読む。
3. 質問文とインデックス行の単語重なりで、関連しそうなドキュメント path を最大 `top_k` 件選ぶ。
4. 各 path に対してツール `nextjs_docs` で本文を取得する。
5. 取得本文をコンテキストとして、設定した Chat モデルに送り、回答を生成する。

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

## ライセンス

リポジトリ側のライセンスに従ってください。`next-devtools-mcp` 本体は npm パッケージのライセンス（MIT）が適用されます。
