import os
import sys
import json
import logging
import datetime

from google.cloud import datastore, firestore

logging.getLogger().setLevel(logging.INFO)


class DBDatastore(object):
    def __init__(self, db_name):
        self.db_client = datastore.Client()
        self.db_name = db_name

    def update_status(self, object_id, bucket_name):
        entity_key = self.db_client.key(self.db_name, object_id)
        entity = self.db_client.get(entity_key)

        if not entity:
            return False

        self.db_client.put(create_updated_entity(entity, object_id, bucket_name))
        return True


class DBFirestore(object):
    def __init__(self, db_name):
        self.db_client = firestore.Client()
        self.db_name = db_name

    def update_status(self, object_id, bucket_name):
        doc_ref = self.db_client.collection(self.db_name).document(object_id)
        doc = doc_ref.get()

        if not doc.exists:
            return False

        doc_ref.update(create_updated_entity(doc, object_id, bucket_name))
        return True


def create_updated_entity(entity, object_id, bucket_name):
    entity['status'] = 'processed'
    entity['url'] = f"https://storage.googleapis.com/{bucket_name}/{object_id}"
    entity['updated_at'] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    return entity


def gcs_entity_processor(data, context):
    logging.debug(context)

    if os.environ.get('FILE_DATABASE_TYPE') not in ['datastore', 'firestore'] or \
            not os.environ.get('FILE_DATABASE_NAME'):
        logging.error("Function does not have correct configuration")
        sys.exit(1)

    db_type = os.environ.get('FILE_DATABASE_TYPE')
    db_name = os.environ.get('FILE_DATABASE_NAME')

    if db_type == 'datastore':
        db_class = DBDatastore(db_name)
    else:
        db_class = DBFirestore(db_name)

    status = db_class.update_status(data['name'], data['bucket'])

    if status:
        logging.info(f"Entity for file '{data['name']}' successfully updated in database '{db_type}/{db_name}'")
    else:
        logging.info(f"Entity for file '{data['name']}' does not exist in database '{db_type}/{db_name}'")


if __name__ == '__main__':
    with open('payload.json', 'r') as json_file:
        payload = json.load(json_file)

    gcs_entity_processor(payload['data'], payload['context'])
