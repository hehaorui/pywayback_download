from attr import has
import httpx
import os
import json
import asyncio
import aiofiles
from queue import Queue


async def __download_coroutine__(q, failedqueue, client, dir=""):
  if not hasattr(__download_coroutine__, "counter"):
    __download_coroutine__.counter = 0
  if not hasattr(__download_coroutine__, "total"):
    __download_coroutine__.total  = q.qsize()
  total = __download_coroutine__.total
  
  if dir != "" and dir[-1] != "/":
    dir += "/"
  
  # The file is a dictionary with the keys "file_url" and "file_path"
  while not q.empty():
    fileItem = await q.get()
    url = fileItem["file_url"]
    path = dir+fileItem["file_path"]
    
    if os.path.exists(path) and os.path.getsize(path) > 0:
      __download_coroutine__.counter += 1
      print(f"File already exists: {path} ({__download_coroutine__.counter}/{total})")
      continue

    try:
      r = await client.get(url, timeout=60)
      if r.status_code != 200:
        raise Exception(f"HTTP error: {r.status_code}")
      
      os.makedirs(os.path.dirname(path), exist_ok=True)
      async with aiofiles.open(path, "wb") as f:
        await f.write(r.content)
      
      __download_coroutine__.counter += 1
      print(f"Downloaded {url} to {path} ({__download_coroutine__.counter}/{total})")
      
    except Exception as e:
      if os.path.exists(path) and os.path.getsize(path) == 0:
        print(f"{path} is empty and was removed.")
        os.remove(path)
      
      __download_coroutine__.counter += 1
      errContent = str(e) if len(str(e))>0 else str(type(e))
      print(f"Failed to download {url}: {errContent} ({__download_coroutine__.counter}/{total})")
      await failedqueue.put(fileItem)

async def download_from_filelist(files, concurrency=10, dir=""):
  failedqueue = asyncio.Queue()
  q = asyncio.Queue()
  for file in files:
    await q.put(file)

  async with httpx.AsyncClient(http2=True) as client:
    coros = [__download_coroutine__(q, failedqueue, client, dir) for _ in range(concurrency)]
    await asyncio.gather(*coros)
  
  failedlist = []
  while not failedqueue.empty():
    failedlist.append(await failedqueue.get())

  return failedlist


def download_from_json(json_file, concurrency=10, parser=None, dir=""):
  with open(json_file, "r") as f:
    files = json.load(f)
  if parser:
    files = parser.parse(files)

  failedlist = asyncio.run(download_from_filelist(files, concurrency, dir))

  with open(dir+"failed.json", "w") as f:
    json.dump(failedlist, f)

class ListParser:
  def __init__(self, mapper):
    self.mapper = mapper

  def parse(self, files):
    return list(map(self.mapper, files))
