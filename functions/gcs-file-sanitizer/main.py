import os
import io
import sys
import logging
import json
import math
import tempfile

import google.auth
import google.auth.transport.requests as tr_requests
import numpy as np

from google.cloud import storage
from google.resumable_media.requests import ChunkedDownload, ResumableUpload

from PIL import Image
from PyPDF2 import PdfFileReader, PdfFileWriter, utils

logging.getLogger().setLevel(logging.INFO)


class GGSFileSanitizer(object):
    def __init__(self):
        self.stg_client = storage.Client()
        self.target_bucket_name = os.environ.get('TARGET_BUCKET_NAME')
        self.max_file_size = int(os.environ.get('MAX_FILE_SIZE', 268435456))  # Defaults to 256MB

        self.credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/devstorage.read_write'])
        self.transport = tr_requests.AuthorizedSession(self.credentials)

        Image.MAX_IMAGE_PIXELS = self.max_file_size

    def sanitize(self, data):
        # Only sanitizing files smaller than 0.5GB
        if int(data['size']) > self.max_file_size:
            logging.info(
                f"File '{data['name']}' too big to process (size: {data['size']}, max: {self.max_file_size}), " +
                "skipping sanitizing")
            sys.exit(0)

        # Only sanitizing files of certain type
        if data['contentType'] not in ['application/pdf', 'image/png', 'image/jpeg']:
            logging.info(
                f"File '{data['name']}' not of type 'application/pdf', 'image/png' or 'image/jpeg', " +
                "skipping sanitizing")
            sys.exit(0)

        logging.info(f"Starting sanitizing of file '{data['name']}'")

        if data['contentType'] in ['image/jpeg', 'image/png']:
            self.process_image(data)
        else:
            self.process_pdf(data)

    def process_image(self, data):
        # Setting chunk sizes
        file_size = int(data['size'])
        chunk_size = 10485760 if file_size > 26214400 else 5242880  # 10MB if file > 25MB else 5MB
        current_chunk = 0

        # Setting streams
        stream_down = io.BytesIO()
        stream_up = io.BytesIO()

        try:
            # Creating Download and Upload objects
            download = ChunkedDownload(data['mediaLink'], chunk_size, stream_down)
            upload = ResumableUpload(
                f"https://www.googleapis.com/upload/storage/v1/b/{self.target_bucket_name}/o?uploadType=resumable",
                chunk_size)

            # Initiate upload
            upload.initiate(
                self.transport, stream_up, {'name': data['name']}, data['contentType'],
                total_bytes=file_size, stream_final=False)

            while download.finished is False:
                logging.debug(f"Processing chunk {current_chunk + 1} of {math.ceil((file_size/chunk_size))}")
                response = download.consume_next_chunk(self.transport)

                na = np.array(response.content)
                sanitized_content = na.tobytes()

                stream_up.write(sanitized_content)
                stream_up.seek(current_chunk * chunk_size)

                upload.transmit_next_chunk(self.transport)
                current_chunk += 1
        except Exception as e:
            logging.exception(e)

    def process_pdf(self, data):
        # Setting chunk sizes
        file_size = int(data['size'])
        chunk_size = 10485760 if file_size > 26214400 else 5242880  # 10MB if file > 25MB else 5MB
        current_chunk = 0

        # Open temporary file
        temp_file = tempfile.TemporaryFile('wb+')

        # Setting download stream
        stream_down = io.BytesIO()
        download = ChunkedDownload(data['mediaLink'], chunk_size, stream_down)

        try:
            while download.finished is False:
                logging.debug(f"Downloading chunk {current_chunk + 1} of {math.ceil((file_size / chunk_size))}")
                response = download.consume_next_chunk(self.transport)

                temp_file.write(response.content)
                current_chunk += 1
        except Exception as e:
            logging.info(
                f"An exception occurred while downloading file '{data['name']}', skipping sanitizing: {str(e)}")
            sys.exit(0)

        writer = PdfFileWriter()
        try:
            reader = PdfFileReader(temp_file, strict=False)
            writer.appendPagesFromReader(reader)

            writer.removeLinks()
        except utils.PdfReadWarning as e:
            logging.info(
                f"A PDF Read Warning occurred when reading PDF file '{data['name']}', continuing sanitizing: {str(e)}")
            pass
        except Exception as e:
            logging.info(
                f"An exception occurred when reading PDF file '{data['name']}', skipping sanitizing: {str(e)}")
            sys.exit(0)

        # Start file upload
        current_chunk = 0
        stream_up = io.BytesIO()
        writer.write(stream_up)
        stream_up.seek(0)

        del writer
        del reader
        temp_file.close()

        try:
            # Start file upload
            upload = ResumableUpload(
                f"https://www.googleapis.com/upload/storage/v1/b/{self.target_bucket_name}/o?uploadType=resumable",
                chunk_size)

            upload.initiate(
                self.transport, stream_up, {'name': data['name']}, data['contentType'],
                total_bytes=stream_up.getbuffer().nbytes)

            while upload.finished is False:
                logging.debug(
                    f"Uploading chunk {current_chunk + 1} of {math.ceil((stream_up.getbuffer().nbytes / chunk_size))}")
                upload.transmit_next_chunk(self.transport)
                current_chunk += 1
        except Exception as e:
            logging.info(
                f"An exception occurred while uploading file '{data['name']}', skipping sanitizing: {str(e)}")
            sys.exit(0)


def gcs_file_sanitizer(data, context):
    logging.debug(context)

    if not os.environ.get('TARGET_BUCKET_NAME'):
        logging.error("Function does not have correct configuration")
        sys.exit(1)

    try:
        GGSFileSanitizer().sanitize(data)
    except MemoryError as error:
        logging.error(error)


if __name__ == '__main__':
    with open('payload_3.json', 'r') as json_file:
        payload = json.load(json_file)

    gcs_file_sanitizer(payload['data'], payload['context'])
