import os
from urllib.parse import urlparse

def wayback_machine_mapper(fileItem):
  baseUrl = "https://web.archive.org/web/"
  
  file_timestamp = fileItem["timestamp"]
  file_id = fileItem["file_id"]
  file_url = fileItem["file_url"]
  
  if file_id == None:
    # speculate file_id from file_url
    parsed = urlparse(file_url)
    file_id = file_timestamp+"/"+parsed.path+"/"+parsed.query+"/"+parsed.fragment
  
  file_path_elements = file_id.split("/")
  file_path_elements = [ e for e in file_path_elements if e != "" ]
  
  if file_id == "":
    file_path = "index.html"
  elif file_url[-1] == "/" or "." not in file_path_elements[-1]:
    file_path = "/".join(file_path_elements)+"/index.html"
  else:
    file_path = "/".join(file_path_elements)
  if os.name == 'nt':  # For Windows
    file_path = file_path.replace("/", "\\")

  file_url =baseUrl+file_timestamp+"_id/"+fileItem["file_url"]
  
  return {"file_url": file_url, "file_path": file_path}