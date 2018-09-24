
import logging
import time
import traceback

# module level logging
logger = logging.getLogger(__name__)

class eptSubscriber(object):
    def __init__(self, fabric):
        # receive instance of Fabric rest object
        self.fabric = fabric

    def run(self):
        """ wrapper around run to handle interrupts/errors """
        logger.info("starting eptSubscriber for fabric '%s'", self.fabric.fabric)
        try:
            self._run()
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            logger.error("Traceback:\n%s", traceback.format_exc())
        finally:
            pass

    def _run(self):
        """ monitor fabric and enqueue work to workers """
        while True:
            time.sleep(1)
            logger.debug("hello from %s", self.fabric.fabric)


