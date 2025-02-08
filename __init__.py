#!/bin/python
import asyncio
from index.index_fetcher import IndexFetcher
from downloader.downloader import Downloader, FileTreeWriter
async def main():
  q = asyncio.Queue()
  idx_fetcher = IndexFetcher(sleep_time=10)
  writer = FileTreeWriter(base_dir="./www.cqu.edu.cn/")
  downloader = Downloader(writer=writer)

  tsk_list = [idx_fetcher.fetchIndex("www.cqu.edu.cn", concurrency=1, out_queue=q), 
              downloader.download(q, concurrency=2, retry=5)]
  await asyncio.gather(*tsk_list)

if __name__ == "__main__":
  asyncio.run(main())
