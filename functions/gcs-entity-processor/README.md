# GCS entity processor

A Google Cloud Function that processes Google Cloud Storage file entities. This function executes when a new file is 
added to a GCS Storage and will update the corresponding entity in the defined Database (see [Database](#database)). 

The following fields will be updated within the entity:
- `status` `[string]`: The status of the current file, defaults to processed;
- `url` `[string]`: The GCS url in format `https://storage.googleapis.com/{bucket_name}/{object_id}`;
- `updated_at` `[string]`: The current timestamp in format `2020-01-01T12:00:00.000Z`.

### Database
This function supports two GCP databases and has to be set by the environment variable `FILE_DATABASE_TYPE`:
- `datastore`: [Google Cloud Datastore](https://cloud.google.com/datastore/docs)
- `firestore`: [Google Cloud Firestore](https://cloud.google.com/firestore/docs)

To select the Database Table name, the environment variable `FILE_DATABASE_NAME` has to be set.

### Deployment to GCP
An example of a Google Cloud Build step is defined within the [cloudbuild.example.yaml](cloudbuild.example.yaml).
Within this example, the variables below need to be updated to your needs:
- `--trigger-resource` `[string]`: The GCS Bucket name the trigger has to execute to;
- `FILE_DATABASE_TYPE` `[string]`: The GCP Database type (see [Database](#database));
- `FILE_DATABASE_NAME` `[string]`: The GCP Database Table name (see [Database](#database)).

### License
This function is licensed under the [GPL-3](https://www.gnu.org/licenses/gpl-3.0.en.html) License
