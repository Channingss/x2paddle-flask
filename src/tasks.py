import threading,time
threading.stack_size(65536)

class Producer(threading.Thread):
    def __init__(self, name, wait_queue, finish_pool, app):
        self.id = None
        self.wait_queue = wait_queue
        self.finish_pool = finish_pool
        threading.Thread.__init__(self, name=name)
        self.daemon=True
        self.result = None
        self.app = app

    def add_task(self,model):
        print("producing %s to the queue!" % (model.id))
        self.id = model.id
        if self.wait_queue.full():
            return False
        self.wait_queue.put(model)
        print("%s finished!" % self.getName())
        return True

    def run(self):
        while True:
            time.sleep(1)
            if self.id in self.finish_pool:
                self.result = self.finish_pool[self.id]
                self.finish_pool.pop(self.id)
                self.app.logger.info(self.id + ' producer get ack success')
                break

class UploadConsumer(threading.Thread):
  def __init__(self, name, wait_queue, finish_queue,app):
    threading.Thread.__init__(self, name=name)
    self.wait_queue = wait_queue
    self.finish_queue = finish_queue
    self.daemon = True
    self.app = app

  def run(self):
    while True:
        time.sleep(1)
        self.app.logger.info('start upload')
        model = self.wait_queue.get()
        self.app.logger.info("%s is consuming. %s in the queue is consumed!" % (self.getName(),model.id))

        model.save()

        self.finish_queue.put(model)
        self.app.logger.info('upload success')

class ConvertConsumer(threading.Thread):
  def __init__(self, name, wait_queue, finish_pool, app):
    threading.Thread.__init__(self, name=name)
    self.wait_queue = wait_queue
    self.finish_pool = finish_pool
    self.daemon = True
    self.app = app
  def run(self):
    while True:
        time.sleep(1)
        model = self.wait_queue.get()
        self.app.logger.info('start convert')
        self.app.logger.info("%s is consuming. %s in the queue is consumed!" % (self.getName(), model.id))

        result = model.convert()

        self.finish_pool[model.id] = result
        self.app.logger.info('convert done')
