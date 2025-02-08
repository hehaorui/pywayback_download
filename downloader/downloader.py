import httpx
import os
import asyncio
import aiofiles
from .page_snapshot import PageSnapshot

class FileWriteError(Exception):
  def __init__(self, message):
    self.message = message
    super().__init__(self.message)

class HTTPError(Exception):
  def __init__(self, message, status_code):
    self.status_code = status_code
    super().__init__(message+f": {status_code}")

class Downloader:
  def __init__(self, writer):
    self.counter = None
    self.failedlist = []
    self.writer = writer

  async def __download_coro__(self, queue, client, retry):
    finished = False
    local_success = 0
    local_failed = 0
    while not finished:
      try:
        d = await queue.get()
        assert(isinstance(d, dict))
      except AssertionError:
        print("\033[91mWrong type of object in queue: ", d, "\033[0m")
      except asyncio.QueueShutDown:
        finished = True
        continue
      snapshot = d["snapshot"]
      tried = d["tried"]
      url = snapshot.get_archive_url()

      try:
        r = await client.get(url, timeout=60)
        tried += 1
        if r.status_code != 200:
            raise HTTPError(f"failed to download {url}", r.status_code)
        snapshot.resp = r
        await self.writer.write(snapshot)
      except Exception as e:
        if tried < retry:
          print(f"Error with {url}: {e}, retry for {retry-tried} times")
          await queue.put({"snapshot": snapshot, "tried": tried})
        else:
          print(f"Error with {url}, failed after {retry} times")
          local_failed += 1
        continue
      self.counter += 1
      local_success += 1
      print(f"Download {url} succeeded (download count: {self.counter})")
    
    return local_success, local_failed

  async def download(self, queue, concurrency=10, retry=5):
    self.counter = 0
    client = httpx.AsyncClient(http2=True)
    coros = [self.__download_coro__(queue, client, retry) for _ in range(concurrency)]
    await asyncio.gather(*coros)
    await client.aclose()
    

class Writer:
  async def write(self, page_snapshot: PageSnapshot):
    raise NotImplementedError
    
class FileTreeWriter(Writer):
  def __init__(self, base_dir):
    if base_dir != "" and base_dir[-1] != os.sep:
      self.base_dir = base_dir + os.sep
    else:
      self.base_dir = base_dir

  async def write(self, page_snapshot: PageSnapshot):
    path = self.base_dir + page_snapshot.get_tree_path()
    if os.path.exists(path) and os.path.getsize(path) > 0:
      print(f"File already exists: {path}")
      return
    
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
      async with aiofiles.open(path, "wb") as f:
        await f.write(page_snapshot.resp.content)
    except Exception as e:
      if os.path.exists(path) and os.path.getsize(path) == 0:
        print(f"{path} is empty and was removed.")
        os.remove(path)
      errContent = str(e) if len(str(e))>0 else str(type(e))
      raise FileWriteError(f"Failed to write {path}: {errContent}")