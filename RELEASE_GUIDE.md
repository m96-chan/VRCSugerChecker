# リリースガイド

GitHub Actionsを使用してVRChat Sugar CheckerのリリースとEXEファイルの配布を行う方法を説明します。

## リリース方法

### 方法1: 手動リリース（推奨）

GitHubのWebインターフェースから手動でリリースをトリガーします。

#### 手順

1. **GitHubリポジトリにアクセス**
   - リポジトリページを開く

2. **Actionsタブをクリック**
   - 上部メニューの「Actions」をクリック

3. **"Build and Release"ワークフローを選択**
   - 左側のワークフロー一覧から「Build and Release」を選択

4. **"Run workflow"をクリック**
   - 右上の「Run workflow」ボタンをクリック

5. **リリース情報を入力**
   - **Branch**: `main` を選択
   - **リリースバージョン**: `v1.0.0` などのバージョン番号を入力
   - **プレリリースとして公開**: 必要に応じてチェック

6. **"Run workflow"を実行**
   - 緑色の「Run workflow」ボタンをクリック

7. **ビルドの完了を待つ**
   - ワークフローが実行され、5〜10分程度でビルドが完了
   - ステータスが緑色のチェックマークになれば成功

8. **リリースを確認**
   - リポジトリの「Releases」タブに新しいリリースが作成される
   - `VRChatSugarChecker.zip` がダウンロード可能になる

### 方法2: タグプッシュで自動リリース

Gitタグをプッシュすると自動的にリリースが作成されます。

#### 手順

```bash
# タグを作成
git tag v1.0.0

# タグをリモートにプッシュ
git push origin v1.0.0
```

タグがプッシュされると、GitHub Actionsが自動的に実行され、リリースが作成されます。

## リリースの流れ

### 1. ビルドジョブ（build）

```
1. リポジトリをチェックアウト
2. Python 3.10をセットアップ
3. 依存関係をインストール（requirements.txt）
4. PyInstallerでビルド
5. 必要なファイルをコピー
   - config.example.json
   - run_silent.vbs
   - install_startup.ps1
   - uninstall_startup.ps1
   - README.md
   - BUILD_GUIDE.md
   - AUDIO_RECORDING.md
6. ZIPファイルを作成
7. アーティファクトをアップロード
```

### 2. リリースジョブ（release）

```
1. ビルドされたZIPファイルをダウンロード
2. バージョン番号を決定
3. GitHubリリースを作成
   - タイトル: VRChat Sugar Checker vX.X.X
   - 説明: 機能一覧と使い方
   - ファイル: VRChatSugarChecker.zip
```

## リリースされるファイル

リリースページからダウンロードできるファイル：

```
VRChatSugarChecker.zip
├── VRChatSugarChecker.exe    # 実行ファイル
├── config.example.json        # 設定ファイルのサンプル
├── run_silent.vbs             # バックグラウンド起動用
├── install_startup.ps1        # スタートアップ登録
├── uninstall_startup.ps1      # スタートアップ削除
├── README.md                  # 使い方
├── BUILD_GUIDE.md             # ビルドガイド
├── AUDIO_RECORDING.md         # 録音機能ガイド
└── logs/
    └── .gitkeep
```

## バージョン管理

### バージョン番号の付け方

セマンティックバージョニング（SemVer）を推奨：

```
vMAJOR.MINOR.PATCH

例:
- v1.0.0  - 初回リリース
- v1.1.0  - 新機能追加
- v1.1.1  - バグフィックス
- v2.0.0  - 破壊的変更
```

### リリースノートの書き方

各リリースには以下の情報を含めると良いです：

```markdown
## v1.1.0 - 2025-01-10

### 新機能
- スクリーンショット自動撮影機能を追加
- Discord通知機能を追加

### 改善
- ログローテーション機能を実装
- パフォーマンスの向上

### バグフィックス
- VRChat終了時にクラッシュする問題を修正

### 既知の問題
- 特になし
```

## トラブルシューティング

### ビルドが失敗する

**原因1: 依存関係の問題**
- `requirements.txt` に必要なパッケージが全て記載されているか確認

**原因2: Specファイルの問題**
- `VRChatSugarChecker.spec` の設定を確認

**解決方法:**
1. ローカルで `build.bat` を実行して確認
2. エラーメッセージを確認
3. 必要に応じて修正してコミット

### リリースが作成されない

**原因: ワークフローの条件**
- `workflow_dispatch` または `push tags` イベントでのみリリースが作成される

**解決方法:**
- 手動実行の場合: Actionsタブから実行
- タグプッシュの場合: `git push origin v1.0.0`

### ZIPファイルにファイルが含まれていない

**原因: コピーステップの失敗**
- ファイルパスが正しいか確認

**解決方法:**
`.github/workflows/release.yml` の「Copy required files」ステップを確認

## GitHub Actionsの設定

### 必要な権限

リポジトリの設定で以下を確認：

1. **Settings** → **Actions** → **General**
2. **Workflow permissions**
   - 「Read and write permissions」を選択
   - 「Allow GitHub Actions to create and approve pull requests」にチェック

### シークレットの設定（不要）

このワークフローは `GITHUB_TOKEN` を使用します。
これは自動的に提供されるため、追加の設定は不要です。

## プレリリース

テスト版をリリースする場合：

1. 手動実行時に「プレリリースとして公開」にチェック
2. または、タグ名に `-beta`, `-rc` を含める
   ```bash
   git tag v1.0.0-beta.1
   git push origin v1.0.0-beta.1
   ```

プレリリースは以下のように表示されます：
- 「Pre-release」バッジが付く
- 最新リリースとして扱われない

## リリース後の作業

### 1. リリースノートの編集

GitHubのリリースページで説明を編集：
- 詳細な変更内容を追加
- スクリーンショットを追加
- 既知の問題を記載

### 2. アナウンス

必要に応じて：
- Discord等で告知
- README.mdを更新
- CHANGELOGを更新

### 3. 検証

リリースされたファイルをダウンロードして動作確認：
1. ZIPファイルをダウンロード
2. 解凍して実行
3. 主要機能をテスト

## 自動化のカスタマイズ

### ビルド対象の変更

複数のプラットフォームに対応する場合：

```yaml
strategy:
  matrix:
    os: [windows-latest, ubuntu-latest, macos-latest]
```

### 通知の追加

DiscordやSlackに通知を送る場合：

```yaml
- name: Notify Discord
  if: success()
  uses: sarisia/actions-status-discord@v1
  with:
    webhook: ${{ secrets.DISCORD_WEBHOOK }}
    status: ${{ job.status }}
```

## まとめ

1. **手動リリース**: GitHub Actionsタブからワンクリックでリリース
2. **自動ビルド**: PyInstallerで自動的にEXEファイルを生成
3. **自動配布**: GitHubリリースページで配布
4. **バージョン管理**: セマンティックバージョニングで管理

これにより、開発者はコードをプッシュするだけで、ユーザーがダウンロードできるリリースパッケージが自動的に作成されます。
