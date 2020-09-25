import os
import sys
from PIL import Image
import logging
import tweepy
from tweepy import TweepError

# NOTE: Need to source the keys file to have the secrets available.
if __name__ == "__main__":
    logging.basicConfig(filename="twitter_bot.log", level=logging.INFO, format='%(asctime)s : %(message)s')
    auth = tweepy.OAuthHandler(
        os.environ.get("API_KEY"), os.environ.get("API_SECRET_KEY")
    )
    auth.set_access_token(
        os.environ.get("ACCESS_TOKEN"), os.environ.get("ACCESS_TOKEN_SECRET")
    )

    api = tweepy.API(auth)

    try:
        api.verify_credentials()
    except TweepError:
        logging.error("Auth failed")
        sys.exit(1)

    filename = sys.argv[1]
    # convert image to jpg to reduce size below 5Mb
    logging.info(f"Compressing image")
    img = Image.open(filename)
    jpeg_filename = filename.replace(".png", ".jpg")
    img.convert("RGB").save(jpeg_filename, optimize=True, quality=90)

    media = api.media_upload(jpeg_filename)

    try:
        api.update_status(status="", media_ids=[media.media_id])
    except TweepError as e:
        logging.error(str(e))
        os.remove(jpeg_filename)
        sys.exit(1)
    logging.info(f"Posted tweet with image {jpeg_filename}")
    os.remove(jpeg_filename)
