from django.contrib import admin
from ..models import Bird, BirdDetail
import requests
import time
import logging
import gc
from django.db import connection

# ロガーの設定
logger = logging.getLogger("app")

@admin.action(description="選択した鳥に対してXeno-Cantoの録音を取得")
def fetch_xeno_canto_recordings(modeladmin, request, queryset):
    base_url = "https://www.xeno-canto.org/api/2/recordings"

    for bird in queryset:
        query = bird.sciName
        params = {
            'query': f"{query} len:0-30 q:A"
        }

        logger.info(f"Requesting recordings for bird: {bird.comName} (Scientific name: {query})")

        try:
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()

            response_size = len(response.content)
            logger.info(f"Response size for {bird.comName}: {response_size} bytes")

            process = psutil.Process()
            mem_info = process.memory_info().rss / (1024 * 1024)
            logger.info(f"Memory usage after request for {bird.comName}: {mem_info:.2f} MB")

        except requests.RequestException as e:
            error_message = f"Failed to fetch data for {bird.comName}: {e}"
            logger.error(error_message)
            modeladmin.message_user(request, error_message, level='error')
            continue

        data = response.json()
        count = 0

        for recording in data.get('recordings', []):
            if count >= 10:
                logger.info(f"10 recordings saved for bird: {bird.comName}")
                break

            if recording.get('q') == 'A':
                recording_url = recording.get('file')
                if not recording_url:
                    logger.warning(f"Recording URL is missing for bird: {bird.comName}")
                    continue

                try:
                    bird_detail, created = BirdDetail.objects.get_or_create(
                        bird_id=bird,
                        recording_url=recording_url,
                    )

                    message = f"Recording {'added' if created else 'already exists'} for {bird.comName}: {recording_url}"
                    logger.info(message)
                    modeladmin.message_user(request, message)

                    count += 1
                    mem_info = process.memory_info().rss / (1024 * 1024)
                    logger.info(f"Memory usage after recording for {bird.comName}: {mem_info:.2f} MB")
                    time.sleep(1)

                except Exception as db_exception:
                    db_error_message = f"Database error for {bird.comName}: {db_exception}"
                    logger.error(db_error_message)
                    modeladmin.message_user(request, db_error_message, level='error')
                    break  # エラーが発生した場合、次の鳥の処理に移行

        # 一時的データを削除し、ガベージコレクションを強制実行
        del data, response
        gc.collect()  
        connection.close()  # DB接続を明示的に閉じる
        time.sleep(5)
        logger.info(f"Finished processing bird: {bird.comName}\n")