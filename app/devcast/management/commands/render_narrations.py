"""The narrator worker: drains the render queue.

Runs as its own container so a hung provider can never occupy a web worker, and
so the billable API key lives in exactly one process.
"""

import signal
import time

from django.core.management.base import BaseCommand

from devcast import conf
from devcast.narration import claim_job, month_char_usage, run_job
from devcast.speech import EngineError, get_engine


class Command(BaseCommand):
    help = "Render queued narrations."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep polling for work.")
        parser.add_argument("--interval", type=int, default=30, help="Seconds between polls.")
        parser.add_argument("--limit", type=int, default=0, help="Stop after N jobs.")
        parser.add_argument("--worker", default=None, help="Lease holder name.")

    def handle(self, *args, **options):
        stopping = False

        def stop(signum, frame):
            nonlocal stopping
            stopping = True
            self.stdout.write("\nfinishing current job, then stopping")

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)

        budget = conf.monthly_char_budget()
        if budget:
            self.stdout.write(f"month usage: {month_char_usage()}/{budget} characters")

        engines = {}
        done = 0
        while not stopping:
            job = claim_job(options["worker"])
            if job is None:
                if not options["loop"]:
                    break
                time.sleep(max(1, options["interval"]))
                continue

            rendition = job.rendition
            self.stdout.write(
                f"rendering {rendition.script_hash[:8]} for page {rendition.page_id} "
                f"(attempt {job.attempts})"
            )
            try:
                engine = engines.setdefault(rendition.engine, get_engine(rendition.engine))
            except EngineError as exc:
                self.stderr.write(str(exc))
                break

            if run_job(job, engine=engine):
                self.stdout.write(self.style.SUCCESS(f"  ready: {rendition.audio.name}"))
            else:
                job.refresh_from_db()
                self.stderr.write(f"  failed: {job.last_error}")

            done += 1
            if options["limit"] and done >= options["limit"]:
                break

        self.stdout.write(f"{done} job(s) processed")
