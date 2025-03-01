import httpx
import os
import asyncio
import aiofiles
from .page_snapshot import PageSnapshot
import warcio.warcwriter
from warcio.statusandheaders import StatusAndHeaders

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
    self.retry = None
    self.tried = None

  async def __download_coro__(self, queue, client, failqueue, waitqueue=False, except_domain=None):
    finished = False
    local_success = 0
    while not finished:
      try:
        snapshot = await queue.get() if waitqueue else queue.get_nowait()
        assert(isinstance(snapshot, PageSnapshot))
      except AssertionError:
        print("\033[91mWrong type of object in queue: ", snapshot, "\033[0m")
      except asyncio.QueueEmpty:
        finished = True
        continue
      except asyncio.QueueShutDown:
        finished = True
        continue
      
      if except_domain and snapshot.get_domain() in except_domain:
        self.counter += 1
        local_success += 1
        print(f"{snapshot.get_archive_url()} skipped because it's in exception list \
               (download count: {self.counter})")
        continue

      if not self.writer.needDownload(snapshot):
        self.counter += 1
        local_success += 1
        print(f"Skip downloading {snapshot.get_archive_url()} (download count: {self.counter})")
        continue
      url = snapshot.get_archive_url()

      try:
        r = await client.get(url, timeout=60)
        if r.status_code != 200 and not str(r.status_code).startswith("3"):
            raise HTTPError(f"HTTP request for {url} failed", r.status_code)
        snapshot.resp = r
        await self.writer.write(snapshot)
      except Exception as e:
        errContent = str(e) if len(str(e))>0 else str(type(e))
        if self.tried < self.retry:
          print(f"Error with {url}: {errContent}, retry for {self.retry-self.tried} times")
        else:
          print(f"Error with {url}: {errContent}, failed after {self.retry} times")
        
        await failqueue.put(snapshot)
        continue
      self.counter += 1
      local_success += 1
      print(f"Download {url} succeeded (download count: {self.counter})")

    return local_success

  async def download(self, queue, concurrency=10, retry=5, except_domain=None):
    self.counter = 0
    self.tried = 0
    self.retry = retry
    client = httpx.AsyncClient(http2=True)
    failqueue = asyncio.Queue()

    # first pass, getting record from IndexFetcher
    self.tried += 1
    coros = [self.__download_coro__(queue, client, failqueue, True, except_domain) for _ in range(concurrency)]
    await asyncio.gather(*coros)
    
    # retry failed pages
    while self.tried < self.retry:
      self.tried += 1
      queue = failqueue
      failqueue = asyncio.Queue()
      coros = [self.__download_coro__(queue, client, failqueue, False, except_domain) for _ in range(concurrency)]
      await asyncio.gather(*coros)
    
    await client.aclose()
    faillist = []
    while not failqueue.empty():
      faillist.append(await failqueue.get())
    return faillist
    

class Writer:
  async def write(self, page_snapshot: PageSnapshot):
    raise NotImplementedError
  
  def needDownload(self, page_snapshot: PageSnapshot):
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
    
  def needDownload(self, page_snapshot: PageSnapshot):
    if page_snapshot.index_record == None:
      return True
    path = self.base_dir + page_snapshot.get_tree_path()
    return not (os.path.exists(path) and os.path.getsize(path) > 0)
  
class MyWARCWriter(Writer):
  def __init__(self, warciowriter: warcio.warcwriter.WARCWriter):
    self.warciowriter: warcio.warcwriter.WARCWriter = warciowriter

  async def write(self, snapshot: PageSnapshot):
    record = snapshot.buildWarcRecord()
    self.warciowriter.write_record(record)
  
  def needDownload(self, page_snapshot: PageSnapshot):
    return True
