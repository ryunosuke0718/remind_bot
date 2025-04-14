# study_Core.py
# このファイルは、Discord Botのコア機能、設定、ロジックを定義します。
# 設定読み込み、発表者管理、メッセージ送信関数、スケジュール関連の準備などを含みます。

# --- ライブラリのインポート ---
import discord          # Discord APIと連携するための基本ライブラリ
import os               # 環境変数（.envファイル）を扱うため
import asyncio          # 非同期処理（Discord.pyの基本）のため
import schedule         # 定期実行のスケジュールを管理するため
from dotenv import load_dotenv # .envファイルから環境変数を読み込むため
from datetime import datetime  # 現在時刻などを扱うため
import traceback        # エラー発生時に詳細情報を表示するため
import json

# --- 設定読み込み ---
load_dotenv() # .envファイルを読み込み
TOKEN = os.getenv('STUDY_REMIND_BOT_TOKEN')
CHANNEL_ID_STR = os.getenv('STUDY_REMIND_CHANNEL_ID')

# チャンネルIDの処理 (エラーチェック含む)
CHANNEL_ID = None
if CHANNEL_ID_STR:
    try:
        CHANNEL_ID = int(CHANNEL_ID_STR)
    except ValueError:
        print(f"設定エラー: .env内のチャンネルID '{CHANNEL_ID_STR}' は有効な数値ではありません。")
        # 必要なら exit() などで終了
else:
    print("設定エラー: .envにチャンネルID (STUDY_REMIND_CHANNEL_ID) が設定されていません。")
    # 必要なら exit() などで終了

# --- 発表者リストの読み込み (.env から JSON形式で) ---
PRESENTERS = [] # デフォルトは空リスト
presenter_json_string = os.getenv('PRESENTER_STUDY')

if presenter_json_string:
    try:
        # JSON文字列をPythonのリスト(辞書のリスト)に変換
        loaded_data = json.loads(presenter_json_string)

        # 読み込んだデータが期待する形式 (辞書のリスト) かチェック
        if isinstance(loaded_data, list) and all(isinstance(p, dict) for p in loaded_data):
            # 各辞書に必要なキー ('name', 'id') があり、IDが整数に変換可能かチェック
            valid_presenters = []
            all_valid = True
            for p in loaded_data:
                if 'name' in p and 'id' in p:
                    try:
                        # IDを整数に変換して格納
                        valid_presenters.append({'name': str(p['name']), 'id': int(p['id'])})
                    except (ValueError, TypeError):
                        print(f"設定警告: .envのPRESENTER_LIST_JSON内のID '{p['id']}' は有効な整数ではありません。スキップします。")
                        all_valid = False
                else:
                    print(f"設定警告: .envのPRESENTER_LIST_JSON内の要素 {p} に 'name' または 'id' がありません。スキップします。")
                    all_valid = False

            if all_valid and valid_presenters: # 全て有効で、かつリストが空でなければ採用
                PRESENTERS = valid_presenters
                print(f"DEBUG: .envから読み込んだ発表者リスト: {PRESENTERS}")
            elif valid_presenters: # 一部無効なデータがあった場合
                PRESENTERS = valid_presenters # 有効なものだけ採用する（要検討）
                print(f"DEBUG: .envから一部無効なデータを除き読み込んだ発表者リスト: {PRESENTERS}")
            else: # 有効なデータが一つもなかった場合
                print("設定エラー: .envのPRESENTER_LIST_JSONから有効な発表者データを読み込めませんでした。")

        else:
            print("設定エラー: .envの PRESENTER_LIST_JSON の形式が不正です（辞書のリストではありません）。")

    except json.JSONDecodeError as e:
        # JSONの形式自体が間違っている場合
        print(f"設定エラー: .envの PRESENTER_LIST_JSON のJSON形式が不正です。エラー: {e}")

else:
    # 環境変数自体が設定されていない場合
    print("警告: .env ファイルに 'PRESENTER_LIST_JSON' が設定されていません。")

# 発表者リストが最終的に空でないかチェック
if not PRESENTERS:
    print("致命的エラー: 利用可能な発表者リストがありません。Botを実行できません。")
    # 適切なエラー処理を行う (例: exit())
    exit("エラー: 発表者リストが空のため終了します。")


# --- 状態変数 (Botが実行中に記憶しておく情報) ---
# 現在の発表者がリストの何番目かを示すインデックス (0から始まる)
# -1 で初期化し、最初のget_current_presenter_info呼び出しで 0 になるようにする
current_presenter_index = -1
# 前回 (send_regular_reminderで通知した) の発表者名を記憶する変数
# send_next_presenter_notification でお疲れ様メッセージに使う
last_presenter_name = None
# 注意: これらの変数はBotプロセスが終了するとリセットされます。

# --- Discordクライアント初期化 ---
# BotがDiscordからどのような情報を受け取るか(Intents)を設定
intents = discord.Intents.default() # デフォルトのIntents
intents.members = True          # サーバーメンバーに関する情報 (参加/退出など) を受け取る場合
intents.message_content = True  # メッセージの内容を読み取る権限が必要な場合
# Discordと通信するためのクライアントオブジェクトを作成
client = discord.Client(intents=intents)

# --- 関数定義 (Botのロジック) ---

def get_current_presenter_info() -> dict | None:
    """
    現在の担当者の情報（名前とIDを含む辞書）を取得し、次の担当者のためにインデックスを進める。
    発表者リストが空の場合は None を返す。
    """
    # ★ global宣言: 関数外で定義された変数の値を変更するため
    global current_presenter_index
    # 発表者リストが設定されているか確認
    if not PRESENTERS:
        print("警告: 発表者リスト(PRESENTERS)が空です。")
        return None
    # インデックスを1つ進める
    current_presenter_index += 1
    # インデックスがリストの範囲を超えたら、0に戻してローテーションさせる
    if current_presenter_index >= len(PRESENTERS):
        current_presenter_index = 0
        print("DEBUG: 発表者リストが一周しました。")
    # 新しいインデックスに対応する発表者の情報（辞書）を取得
    selected_presenter_info = PRESENTERS[current_presenter_index]
    # デバッグ用に現在のインデックスと選ばれた発表者情報を表示
    print(f"DEBUG: 今回の発表者インデックス: {current_presenter_index}, 情報: {selected_presenter_info}")
    # 発表者の情報（辞書）を返す
    return selected_presenter_info

def get_next_presenter_info() -> dict | None:
    """
    次回の担当者の情報（名前とIDを含む辞書）を取得する。
    この関数はインデックスを進めない。
    発表者リストが空の場合は None を返す。
    """
    # ★ global宣言: 関数外で定義された変数の値を読み取るため (変更はしないが明示的に)
    global current_presenter_index
    # 発表者リストが設定されているか確認
    if not PRESENTERS: return None
    # 現在のインデックス (今回担当した人) の次を計算する
    # % len(PRESENTERS) でリストの末尾に来たら先頭 (0) に戻る
    next_index = (current_presenter_index + 1) % len(PRESENTERS)
    # 次のインデックスに対応する発表者の情報（辞書）を取得
    next_presenter_info = PRESENTERS[next_index]
    # デバッグ用に次回インデックスと発表者情報を表示
    print(f"DEBUG: 次回発表者インデックス: {next_index}, 情報: {next_presenter_info}")
    # 次回発表者の情報（辞書）を返す
    return next_presenter_info

async def send_regular_reminder(client_instance: discord.Client, channel_id: int):
    """
    通常の定期リマインドを送信する関数。
    @everyoneメンションと今回の担当者名を通知し、今回の担当者名を保存する。
    """
    # ★ global宣言: 関数外の last_presenter_name 変数を変更するため
    global last_presenter_name
    print(f"DEBUG: send_regular_reminder called at {datetime.now()}")
    # 指定されたチャンネルIDからチャンネルオブジェクトを取得
    channel = client_instance.get_channel(channel_id)
    # チャンネルが存在し、かつテキストチャンネルであることを確認
    if not (channel and isinstance(channel, discord.TextChannel)):
        if channel: print(f"エラー: Ch ID {channel_id} はテキストチャンネルではない。Type: {type(channel)}")
        else: print(f"エラー: Ch ID {channel_id} が見つからない。")
        return # 処理中断
    try:
        # 今回の担当者情報を取得（ここで current_presenter_index が進む）
        presenter_info = get_current_presenter_info()
        # 担当者情報が取得できなかった場合（リストが空など）は処理中断
        if presenter_info is None:
            print("エラー: 担当者情報取得失敗。通常リマインドスキップ。")
            return
        # 担当者名を取得
        presenter_name = presenter_info['name']
        # メッセージを作成 (@everyone と担当者名を含む)
        message = f"@everyone\n勉強会の時間です！\n今回の担当は **{presenter_name}** さんです。"
        # メッセージを送信 (await で完了を待つ)
        await channel.send(message)
        # 送信ログを出力
        print(f"通常リマインダー送信: {datetime.now()} (担当: {presenter_name})")

        # ★ 今回の発表者名をグローバル変数に保存 (次回通知メッセージで使用するため)
        last_presenter_name = presenter_name
        print(f"DEBUG: 今回の発表者名を保存: {last_presenter_name}")

    except discord.Forbidden: # Botに送信権限がない場合のエラー
        print(f"エラー: Ch {channel.name} ({channel.id}) 送信権限なし。")
    except Exception as e: # その他の予期せぬエラー
        print(f"通常リマインダー送信処理中エラー: {e}")
        traceback.print_exc() # 詳細なエラー情報を表示

async def send_next_presenter_notification(client_instance: discord.Client, channel_id: int):
    """
    次回の発表者へメンション付きで通知する関数。
    （可能であれば）前回担当者への労いの言葉も添える。
    """
    # ★ global宣言: 関数外の last_presenter_name 変数を読み取るため
    global last_presenter_name
    print(f"DEBUG: send_next_presenter_notification called at {datetime.now()}")
    channel = client_instance.get_channel(channel_id)
    if not (channel and isinstance(channel, discord.TextChannel)):
        # エラーログ (省略)
        return
    try:
        # 次回の担当者情報を取得 (インデックスは変更しない)
        next_presenter_info = get_next_presenter_info()
        # 担当者情報が取得できなかった場合（リストが空など）は処理中断
        if next_presenter_info is None:
            print("エラー: 次回担当者情報取得失敗。次回通知スキップ。")
            return
        # 次回担当者の名前とIDを取得
        next_presenter_name = next_presenter_info['name']
        next_presenter_id = next_presenter_info['id']
        # Discordのメンション形式 (<@ユーザーID>) の文字列を作成
        mention = f"<@{next_presenter_id}>"

        # メッセージを作成
        if last_presenter_name:
            # 前回担当者の名前が保存されていれば、お疲れ様メッセージを追加
            message = f"**{last_presenter_name}** さん、発表お疲れ様でした！👏\n📢 次回の担当は {mention} さんです。\n準備よろしくお願いします！"
            print(f"DEBUG: 次回通知メッセージ作成 (前回担当者: {last_presenter_name})")
        else:
            # 前回担当者の名前がない場合（Bot起動後初回など）はシンプルなメッセージ
            message = f"📢 次回の勉強会担当は {mention} さんです。\n発表に向けて資料の準備よろしくお願いします！"
            print("DEBUG: 前回担当者情報が見つからないため、シンプルな次回通知メッセージを作成")

        # メッセージを送信
        await channel.send(message)
        # 送信ログを出力
        print(f"次回発表者通知 送信: {datetime.now()} (次回担当: {next_presenter_name})")

    except discord.Forbidden: # 送信権限エラー
        print(f"エラー: Ch {channel.name} ({channel.id}) 送信権限なし（次回通知）。")
    except Exception as e: # その他のエラー
        print(f"次回発表者通知 送信処理中エラー: {e}")
        traceback.print_exc()

# --- スケジュール連携ラッパー関数 ---
# scheduleライブラリは同期的、discord.pyは非同期なので、直接非同期関数を呼べない。
# そのため、scheduleから呼び出される同期関数(ラッパー)を用意し、
# その中で非同期関数を安全に呼び出す。

def regular_reminder_job():
    """ 通常リマインド用の同期ラッパー関数 """
    print(f"DEBUG: regular_reminder_job called by schedule at {datetime.now()}")
    # Botが完全に起動していて、イベントループが動作中か確認
    if client.is_ready() and client.loop.is_running():
        # asyncio.run_coroutine_threadsafe:
        #   現在のスレッドから、Botのメインイベントループ上で非同期関数を実行させるための関数
        asyncio.run_coroutine_threadsafe(
            send_regular_reminder(client, CHANNEL_ID), # 実行したい非同期関数と引数
            client.loop # Botのイベントループを指定
        )
    else:
        # Bot起動直後などでまだ準備ができていない場合
        print("DEBUG: Bot not ready or loop not running in regular_reminder_job. Skipping.")

def next_presenter_notification_job():
    """ 次回発表者通知用の同期ラッパー関数 """
    print(f"DEBUG: next_presenter_notification_job called by schedule at {datetime.now()}")
    if client.is_ready() and client.loop.is_running():
        asyncio.run_coroutine_threadsafe(
            send_next_presenter_notification(client, CHANNEL_ID),
            client.loop
        )
    else:
        print("DEBUG: Bot not ready or loop not running in next_presenter_notification_job. Skipping.")

# --- スケジュール設定 ---
# scheduleライブラリを使って、いつ、どの関数を呼び出すか登録する
# !!重要!!: 実行したい時刻に合わせてコメントアウトを解除・編集してください
# !!注意!!: `next_presenter_notification_job` は `regular_reminder_job` より後の時刻に設定してください。

# 例1: 本番用 - 日曜日の10:30に通常リマインド、11:30に次回発表者通知
#schedule.every().sunday.at("10:30").do(regular_reminder_job)
#schedule.every().sunday.at("11:30").do(next_presenter_notification_job)
#print("本番用スケジュール設定: 日曜 10:30 (通常), 11:30 (次回発表者)")

# 例2: デバッグ用 - 毎分5秒に通常リマインド、毎分15秒に次回発表者通知
#       schedule.every().minute.at("秒数") で指定
schedule.every().minute.at(":05").do(regular_reminder_job)
schedule.every().minute.at(":15").do(next_presenter_notification_job)
print("デバッグ用スケジュール設定: 毎分 :05 (通常), :15 (次回発表者)")

# --- スケジュール監視ループ関数 (非同期) ---
async def run_scheduler():
    """
    scheduleライブラリで登録されたジョブを実行するタイミングか、
    1秒ごとにチェックし続けるための非同期関数。
    """
    print("スケジューラーループを開始します。")
    # 無限ループで動き続ける
    while True:
        # 1秒間、他の処理に制御を譲りつつ待機
        await asyncio.sleep(1)
        try:
            # 現在時刻を確認し、実行すべきスケジュールがあれば実行する
            schedule.run_pending()
        except Exception as e:
            # スケジュール実行中にエラーが起きてもループは止めない
            print(f"スケジューラー実行中にエラーが発生しました: {e}")
            traceback.print_exc()

# --- Discord イベントハンドラ ---
# @client.event デコレータ: Discord側で特定のイベントが発生した時に下の関数を実行するよう登録
@client.event
async def on_ready():
    """ BotがDiscordに接続し、準備が完了した時に呼び出される関数 """
    print("-" * 30)
    # Bot自身の情報を表示
    if client.user:
        print(f'{client.user.name} としてログインしました (ID: {client.user.id})')
    else:
        print("Botユーザー情報が取得できませんでした。")

    # 設定されたチャンネルIDと、実際にそのチャンネルが見つかるか確認
    if CHANNEL_ID:
        print(f'リマインド対象チャンネルID: {CHANNEL_ID}')
        target_channel = client.get_channel(CHANNEL_ID)
        if target_channel and isinstance(target_channel, discord.TextChannel):
            print(f'リマインド対象チャンネル名: #{target_channel.name}')
        elif target_channel:
            print(f'警告: チャンネルID {CHANNEL_ID} はテキストチャンネルではありません。タイプ: {type(target_channel)}')
        else:
            # IDが間違っているか、Botがそのサーバーに参加していない可能性
            print(f'警告: チャンネルID {CHANNEL_ID} が見つかりません。IDやBotの参加サーバーを確認してください。')
    else:
        print("警告: リマインド対象チャンネルIDが設定されていません。")

    # 発表者リストが空でないか確認
    if not PRESENTERS:
        print("警告: 発表者リスト (PRESENTERS) が空になっています。")

    print("-" * 30)
    # スケジュール監視ループをバックグラウンドタスクとして開始する
    # これにより、Botが他のイベントを処理しながら、スケジュールも監視できる
    asyncio.create_task(run_scheduler())

# このファイルが import されたときに基本的な準備が完了したことを示すメッセージ
print("reminder_bot.py loaded: Bot logic, configuration, client setup, and event handlers ready.")