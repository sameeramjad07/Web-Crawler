import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
import json
import os
import pickle
import logging
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
from wordcloud import WordCloud
from mpi4py import MPI
from config import Config
import argparse

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MPIDistributedCrawler:
    def __init__(self, config, comm, rank, size):
        """Initialize the MPI distributed crawler."""
        self.config = config
        self.comm = comm
        self.rank = rank
        self.size = size
        self.root_url = f"{urlparse(config.SEED_URL).scheme}://{urlparse(config.SEED_URL).netloc}"
        self.output_dir = config.OUTPUT_DIR

    def fetch_page(self, url):
        """Fetch a web page and return its response or None if it fails."""
        try:
            response = requests.get(url, timeout=(3, 30))
            if response.status_code == 200:
                return response
            else:
                logger.warning(f"Worker {self.rank} failed to fetch {url}: Status code {response.status_code}")
                return None
        except requests.RequestException as e:
            logger.error(f"Worker {self.rank} error fetching {url}: {e}")
            return None

    def extract_data(self, soup, url, depth):
        """Extract specified data from the page."""
        extracted_data = {'url': url, 'depth': depth}
        for item in self.config.DATA_TO_EXTRACT:
            try:
                if item == 'title':
                    title_tag = soup.find('title')
                    extracted_data['title'] = title_tag.text.strip() if title_tag else 'No Title'
                elif item == 'meta_description':
                    meta_tag = soup.find('meta', attrs={'name': 'description'})
                    extracted_data['meta_description'] = meta_tag['content'].strip() if meta_tag and 'content' in meta_tag.attrs else 'No Meta Description'
                elif item.startswith('.'):
                    elements = soup.select(item)
                    extracted_data[item] = [elem.text.strip() for elem in elements]
                else:
                    elements = soup.find_all(item)
                    extracted_data[item] = [elem.text.strip() for elem in elements]
            except Exception as e:
                logger.error(f"Worker {self.rank} error extracting {item} from {url}: {e}")
                extracted_data[item] = []
        return extracted_data

    def parse_links(self, soup):
        """Parse HTML to extract links."""
        links = []
        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            full_url = urljoin(self.root_url, href)
            if full_url.startswith(self.root_url):
                links.append(full_url)
        return links

    def master(self):
        """Master process: Assign URLs and collect results."""
        urls_to_crawl = [(self.config.SEED_URL, 0)]  # (url, depth)
        visited_urls = set()
        results = []
        pages_crawled = 0
        idle_workers = list(range(1, self.size))
        active_tasks = {}  # worker_rank -> (url, depth)

        start_time = time.time()

        # Main loop
        while pages_crawled < self.config.MAX_PAGES and (urls_to_crawl or active_tasks):
            # Assign tasks to idle workers
            while idle_workers and urls_to_crawl and pages_crawled < self.config.MAX_PAGES:
                url, depth = urls_to_crawl.pop(0)
                if url in visited_urls or depth > self.config.MAX_DEPTH:
                    continue
                visited_urls.add(url)
                worker = idle_workers.pop(0)
                self.comm.send((url, depth), dest=worker, tag=1)
                active_tasks[worker] = (url, depth)
                pages_crawled += 1
                logger.info(f"Master assigned {url} to worker {worker} (Depth: {depth})")

            # Collect results from workers
            for worker in list(active_tasks.keys()):
                if self.comm.Iprobe(source=worker, tag=2):
                    data = self.comm.recv(source=worker, tag=2)
                    extracted_data, links = pickle.loads(data)
                    if extracted_data:
                        results.append(extracted_data)
                    for link in links:
                        if link not in visited_urls:
                            urls_to_crawl.append((link, active_tasks[worker][1] + 1))
                    idle_workers.append(worker)
                    del active_tasks[worker]
                    logger.info(f"Master received results from worker {worker}")

        # Terminate idle workers
        for worker in idle_workers:
            self.comm.send(None, dest=worker, tag=1)

        # Collect remaining results and terminate active workers
        for worker in list(active_tasks.keys()):
            data = self.comm.recv(source=worker, tag=2)
            extracted_data, links = pickle.loads(data)
            if extracted_data:
                results.append(extracted_data)
            for link in links:
                if link not in visited_urls:
                    urls_to_crawl.append((link, active_tasks[worker][1] + 1))
            self.comm.send(None, dest=worker, tag=1)
            logger.info(f"Master received final results from worker {worker}")

        end_time = time.time()
        execution_time = end_time - start_time
        pages_per_second = pages_crawled / execution_time if execution_time > 0 else 0

        logger.info(f"Crawl completed. Pages crawled: {pages_crawled}")
        logger.info(f"Execution time: {execution_time:.2f} seconds")
        logger.info(f"Pages per second: {pages_per_second:.2f}")

        # Save and visualize results
        self.save_results(results)
        self.generate_visualizations(results)

        return {
            'pages_crawled': pages_crawled,
            'execution_time': execution_time,
            'pages_per_second': pages_per_second
        }

    def worker(self):
        """Worker process: Fetch URLs and return results."""
        while True:
            # Receive task from master
            task = self.comm.recv(source=0, tag=1)
            if task is None:
                break
            url, depth = task

            logger.info(f"Worker {self.rank} processing {url} (Depth: {depth})")

            # Fetch and process page
            response = self.fetch_page(url)
            if not response:
                self.comm.send(pickle.dumps((None, [])), dest=0, tag=2)
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            extracted_data = self.extract_data(soup, url, depth)
            links = self.parse_links(soup)

            # Send results to master
            self.comm.send(pickle.dumps((extracted_data, links)), dest=0, tag=2)

    def save_results(self, results):
        """Save crawled data to a JSON file."""
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, 'results.json')
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=4)
        logger.info(f"Results saved to {output_path}")

    def generate_visualizations(self, results):
        """Generate visualizations for crawled data."""
        os.makedirs(self.output_dir, exist_ok=True)

        # Bar Chart: Pages per Depth
        depths = [result['depth'] for result in results]
        depth_counts = {}
        for depth in range(self.config.MAX_DEPTH + 1):
            depth_counts[depth] = depths.count(depth)
        
        plt.figure(figsize=(8, 6))
        plt.bar(depth_counts.keys(), depth_counts.values(), color='skyblue')
        plt.xlabel('Crawl Depth')
        plt.ylabel('Number of Pages')
        plt.title('Pages Crawled per Depth')
        plt.grid(True, axis='y')
        plt.savefig(os.path.join(self.output_dir, 'depth_distribution.png'))
        plt.close()
        logger.info("Generated depth distribution bar chart")

        # Word Cloud: Extracted Text
        all_text = []
        for result in results:
            for key, value in result.items():
                if key in self.config.DATA_TO_EXTRACT and isinstance(value, list):
                    all_text.extend(value)
                elif key in self.config.DATA_TO_EXTRACT and isinstance(value, str):
                    all_text.append(value)
        text = ' '.join(all_text)
        if text.strip():
            wordcloud = WordCloud(width=800, height=400, background_color='white').generate(text)
            plt.figure(figsize=(10, 5))
            plt.imshow(wordcloud, interpolation='bilinear')
            plt.axis('off')
            plt.title('Word Cloud of Extracted Content')
            plt.savefig(os.path.join(self.output_dir, 'word_cloud.png'))
            plt.close()
            logger.info("Generated word cloud")
        else:
            logger.warning("No text available for word cloud")

    def run(self):
        """Run the MPI distributed crawler."""
        if self.rank == 0:
            metrics = self.master()
            print(f"\nSummary:")
            print(f"Pages Crawled: {metrics['pages_crawled']}")
            print(f"Execution Time: {metrics['execution_time']:.2f} seconds")
            print(f"Pages per Second: {metrics['pages_per_second']:.2f}")
            return metrics
        else:
            self.worker()
            return None

def main():
    parser = argparse.ArgumentParser(description="MPI distributed web crawler")
    parser.add_argument('--config', default='config.Config', help='Config class to use (default: config.Config)')
    args = parser.parse_args()

    comm = MPI.COMM_WORLD
    rank = comm.Get_rank()
    size = comm.Get_size()

    if size < 2:
        if rank == 0:
            logger.error("At least 2 processes are required (1 master + 1 worker)")
        return

    config = Config()
    crawler = MPIDistributedCrawler(config, comm, rank, size)
    crawler.run()

if __name__ == '__main__':
    main()