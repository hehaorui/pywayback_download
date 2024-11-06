import requests
import os
import json
import threading
from queue import Queue


def __download_worker__(q, failedqueue, counter, dir=""):
  # The file is a dictionary with the keys "file_url" and "file_path"
  if dir != "" and dir[-1] != "/":
    dir += "/"
  download_total = counter["TOTAL"]
  
  while not q.empty():
    fileItem = q.get()
    url = fileItem["file_url"]
    path = dir+fileItem["file_path"]
    
    if os.path.exists(path) and os.path.getsize(path) > 0:
      with counter["lock"]:
        counter["value"] += 1
        download_count = counter["value"]
        print(f"File already exists: {path} ({download_count}/{download_total})")
      continue

    try:
      r = requests.get(url, timeout=10)
      if r.status_code != 200:
        raise Exception(f"HTTP error: {r.status_code}")
      
      os.makedirs(os.path.dirname(path), exist_ok=True)
      with open(path, "wb") as f:
        f.write(r.content)
      with counter["lock"]:
        counter["value"] += 1
        download_count = counter["value"]
        print(f"Downloaded {url} to {path} ({download_count}/{download_total})")
      
    except Exception as e:
      file_remove = os.path.exists(path) and os.path.getsize(path) == 0
      if file_remove:
        os.remove(path)
      
      with counter["lock"]:
        counter["value"] += 1
        download_count = counter["value"]
        print(f"Failed to download {url}: {e} ({download_count}/{download_total})")
        if file_remove:
          print(f"{path} is empty and was removed.")
      failedqueue.put(fileItem)

def download_from_filelist(files, thread_count=10, dir=""):
  failedqueue = Queue()
  q = Queue()
  for file in files:
    q.put(file)

  threads = []
  counter = {"lock": threading.Lock(), "value": 0, "TOTAL": len(files)}

  for _ in range(thread_count):
    t = threading.Thread(target=__download_worker__, args=(q, failedqueue, counter, dir))
    t.start()
    threads.append(t)

  for t in threads:
    t.join()

  failedlist = []
  while not failedqueue.empty():
    failedlist.append(failedqueue.get())

  return failedlist


def download_from_json(json_file, thread_count=10, parser=None, dir=""):
  with open(json_file, "r") as f:
    files = json.load(f)
  if parser:
    files = parser.parse(files)

  failedlist = download_from_filelist(files, thread_count, dir)

  with open(dir+"failed.json", "w") as f:
    json.dump(failedlist, f)

class ListParser:
  def __init__(self, mapper):
    self.mapper = mapper

  def parse(self, files):
    return list(map(self.mapper, files))
