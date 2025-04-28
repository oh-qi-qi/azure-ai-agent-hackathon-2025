"""Test script to verify Azure Storage connection and file upload."""

import os
from datetime import datetime
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_azure_storage_upload():
    """Test Azure Storage upload functionality with a dummy text file."""
    
    # Get configuration from environment
    storage_connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    storage_container = os.getenv("AZURE_STORAGE_CONTAINER", "procurement-expediting-risk-reports")
    storage_account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
    
    # Initialize blob service client
    blob_service_client = None
    
    try:
        # Try connection string first
        if storage_connection_string:
            print("Using connection string for authentication...")
            blob_service_client = BlobServiceClient.from_connection_string(storage_connection_string)
        elif storage_account_name:
            # Use DefaultAzureCredential if no connection string
            print("Using DefaultAzureCredential for authentication...")
            credential = DefaultAzureCredential()
            account_url = f"https://{storage_account_name}.blob.core.windows.net"
            blob_service_client = BlobServiceClient(account_url, credential=credential)

        else:
            raise ValueError("Neither AZURE_STORAGE_CONNECTION_STRING nor AZURE_STORAGE_ACCOUNT_NAME is set")
        
        # Get container client
        container_client = blob_service_client.get_container_client(storage_container)
        
        # Create container if it doesn't exist
        try:
            container_client.create_container()
            print(f"Created container: {storage_container}")
        except Exception as e:
            if "ContainerAlreadyExists" in str(e):
                print(f"Container already exists: {storage_container}")
            else:
                raise
        
        # Create a dummy text file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"test_file_{timestamp}.txt"
        local_path = f"./test_{timestamp}.txt"
        
        # Write some test content
        test_content = f"""
            Test File Upload
            Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            Purpose: Verify Azure Storage connectivity and upload functionality
            Container: {storage_container}
        """
        
        with open(local_path, 'w') as f:
            f.write(test_content)
        
        print(f"Created local test file: {local_path}")
        
        # Upload the file
        blob_path = f"test/{filename}"
        blob_client = container_client.get_blob_client(blob_path)
        
        with open(local_path, "rb") as data:
            blob_client.upload_blob(
                data, 
                overwrite=True,
                content_settings=ContentSettings(content_type="text/plain")
            )
        
        print(f"Successfully uploaded file to: {blob_path}")
        print(f"Blob URL: {blob_client.url}")
        
        # List blobs in the container to verify
        print("\nListing blobs in container:")
        blobs = container_client.list_blobs()
        for blob in blobs:
            print(f"- {blob.name}")
        
        # Clean up local file
        os.remove(local_path)
        print(f"\nCleaned up local file: {local_path}")
        
        return True
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Starting Azure Storage test...")
    success = test_azure_storage_upload()
    
    if success:
        print("\n✅ Azure Storage test completed successfully!")
    else:
        print("\n❌ Azure Storage test failed!")
