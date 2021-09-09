# docker based quay fullstack deployment using ansible
See playbooks, set your variables and enjoy

ETA: WIP/not finished, may not be done

we didnt validated the solution (leaks in object storage, overall stability)


- can be used behind a SSL offloader
- adds a fail2ban integration to ban brute force attacks



To store in ovh PCS, we needed to patch the cloud s3 backend this way
```python
/quay-registry/storage/cloud.py
 
class S3Storage(_CloudStorage):
    def __init__(
        self,
        context,
        storage_path,
        s3_bucket,
        s3_access_key=None,
        s3_secret_key=None,
        # Boto2 backward compatible options (host excluding scheme or port)
        host=None,
        port=None,
        # Boto3 options (Full url including scheme anbd optionally port)
        endpoint_url=None,
        encryption=True,
        config=None,
        upload_params=None,
    ):
        if config is None:
            config = {}
        if upload_params is None:
            upload_params = {}
        if encryption:
            upload_params.setdefault("ServerSideEncryption", "AES256")
        config.setdefault("signature_version", "s3v4")
        connect_kwargs = {"config": Config(**config)}
        if host or endpoint_url:
            connect_kwargs["endpoint_url"] = endpoint_url or _build_endpoint_url(
                host, port=port, is_secure=True
            )                                      
```
