import os
import sys
from PIL import Image
import logging
import tweepy

# NOTE: Need to source the keys file to have the secrets available.
logging.basicConfig(filename='twitter_bot.log',)

if __name__ == '__main__':
    auth = tweepy.OAuthHandler(os.environ.get("API_KEY"), os.environ.get("API_SECRET_KEY"))
    auth.set_access_token(os.environ.get("ACCESS_TOKEN"), os.environ.get("ACCESS_TOKEN_SECRET"))

    api = tweepy.API(auth)

    filename = sys.argv[1]
    # convert image to jpg to reduce size below 5Mb
    logging.info(f'Compressing image')
    img = Image.open(filename)
    jpeg_filename = filename.replace('.png', '.jpg') 
    img.convert('RGB').save(jpeg_filename, optimize=True, quality=90)
    
    media = api.media_upload(jpeg_filename)

    try:
        api.update_status(status='', media_ids=[media.media_id])
    except Exception as e:
        logging.error(str(e))
        os.remove(jpeg_filename)
        sys.exit(1)
    logging.info(f'Posted tweet with image {jpeg_filename}')
    os.remove(jpeg_filename)

