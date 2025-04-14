
# このファイルを実行してBotを起動します。
import journal_Core # ここを変更

# discord エラークラスのためにインポート
import discord
import traceback

# --- Bot起動 ---
if __name__ == "__main__":
    print("Botの起動プロセスを開始します...")

    # 起動前に設定値を確認 (journal_Coreから読み込む)
    if journal_Core.TOKEN is None: # 参照元を変更
        print("起動エラー: Botトークンが設定されていません。 .env と journal_Core を確認してください。")
    elif journal_Core.CHANNEL_ID is None: # 参照元を変更
        print("起動エラー: チャンネルIDが設定されていないか無効です。 .env と journal_Core を確認してください。")
    # 発表者リストが空でも起動は試みる（警告はon_readyで出す）
    else:
        try:
            print("Discordに接続し、Botを起動します...")
            # journal_Core で定義・準備された client と TOKEN を使って Bot を実行
            journal_Core.client.run(journal_Core.TOKEN) # 参照元を変更
        except discord.LoginFailure:
            print("起動エラー: 不正なDiscord Botトークンです。 .env ファイルを確認してください。")
        except discord.PrivilegedIntentsRequired as e:
            shard_info = f"Shard ID: {e.shard_id}" if e.shard_id is not None else "N/A"
            print(f"起動エラー: Privileged Gateway Intents ({shard_info}) が有効になっていません。")
            print("Discord Developer Portal でBotの設定を確認してください。")
        except Exception as e:
            print(f"Bot実行中に予期せぬエラーが発生しました: {e}")
            traceback.print_exc()