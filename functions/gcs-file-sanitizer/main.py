import logging


def gcs_file_sanitizer(data, context):
    """Background Cloud Function to be triggered by Cloud Storage.
       This function sanitizes new files (max 0.5GB) and moves them towards a target bucket.

    Args:
        data (dict): The Cloud Functions event payload.
        context (google.cloud.functions.Context): Metadata of triggering event.
    """

    logging.info(data)
    logging.info(context)
