""" Python threading is useless in the context of symmetric multiprocessor
(SMP) machines because the interpreter data structures are not thread-safe.
As a result, a global interpreter lock (GIL) ensures that one and only one
thread can run the interpreter at any time. As a result, it is impossible
to concurrently run Python functions on several processors. The BDL has made
it quite clear the situation will not change in the foreseeable future.

However multiprocessor machines are now mundane. Hence this module. For the
time being, only UNIX systems are supported, through the use of 'fork'.
"""

from __future__ import generators, division
from libtbx import forward_compatibility
from libtbx.utils import tupleize
from libtbx import easy_pickle
import sys, os, select
import cStringIO, cPickle


class parallelized_function(object):

  def __init__(self, func, max_children, timeout=0.001, printout=None):
    if (printout is None): printout = sys.stdout
    if 'fork' not in os.__dict__:
      raise NotImplementedError("Only works on platforms featuring 'fork',"
                                "i.e. UNIX")
    self.func = func
    self.max_children = max_children
    self.timeout = timeout
    self.printout = printout
    self.child_pid_for_out_fd = {}
    self.index_of_pid = {}
    self.next_i = 0
    self.result_queue = []
    self.debug = False

  def child_out_fd(self):
    return self.child_pid_for_out_fd.keys()
  child_out_fd = property(child_out_fd)

  def poll(self):
    if len(self.child_out_fd) == self.max_children:
      if self.debug: print "** waiting for a child to finish **"
      inputs, outputs, errors = select.select(self.child_out_fd, [], [])
    else:
      inputs, outputs, errors = select.select(self.child_out_fd, [], [],
                                              self.timeout)
    if not inputs:
      if self.debug: print "\tno file descriptor is ready"
    else:
      if self.debug: print "\tfile descriptor%s %s %s ready" % (
        ('','s')[len(inputs)>1],
        ', '.join(["%i" % pid for pid in inputs]),
        ('is', 'are')[len(inputs)>1])
    for fd in inputs:
      f = os.fdopen(fd)
      msg = f.read() # block only shortly because of the child buffering
      l = int(msg[:128], 16)
      result = cPickle.loads(msg[128:128+l])
      print >> self.printout, msg[128+l:],
      pid = self.child_pid_for_out_fd.pop(fd)
      j = self.index_of_pid.pop(pid)
      os.waitpid(pid, 0) # to make sure the child is fully cleaned up
      if self.debug: print "#%i -> %s" % (j, result)
      self.result_queue.append((j, result))
    for i, (j,x) in enumerate(sorted(self.result_queue)):
      if j == self.next_i:
        self.next_i += 1
        del self.result_queue[i]
        yield x
      else:
        break

  def __call__(self, iterable):
    for i,x in enumerate(iterable):
      args = tupleize(x)
      r,w = os.pipe()
      pid = os.fork()
      if pid > 0:
        # parent
        if self.debug: print "parent: from %i, child %i: to %i" % (r, pid, w)
        os.close(w)
        self.child_pid_for_out_fd[r] = pid
        self.index_of_pid[pid] = i
        for result in self.poll():
          yield result
      else:
        # child
        os.close(r)
        # fully buffer the print-out of the wrapped function
        output = cStringIO.StringIO()
        sys.stdout, stdout = output, sys.stdout
        result = self.func(*args)
        sys.stdout = stdout
        if self.debug: print "\tchild writing to %i" % w
        f = os.fdopen(w, 'w')
        pickled_result = easy_pickle.pickled(result)
        msg = ''.join((
          "%128x" % len(pickled_result),
          pickled_result,
          output.getvalue()))
        print >> f, msg,
        try:f.close()
        except KeyboardInterrupt: raise
        except:pass
        os._exit(0)
    while self.child_out_fd:
      for result in self.poll():
        yield result


def exercise():
  import math, time, re
  from libtbx.test_utils import approx_equal
  from libtbx.utils import show_times_at_exit
  show_times_at_exit()
  def func(i):
    s = 0
    n = 8e5
    h = math.pi/2/n
    for j in xrange(int(n)):
      s += math.cos(i*j*h)
    s = abs(s*h)
    print "%i:" % i,
    time.sleep(0.05)
    print "S=%.2f" % s
    return s

  try:
    result_pat = re.compile("(\d+): S=(\d\.\d\d)")
    ref_results = [ abs(math.sin(i*math.pi/2)/i) for i in xrange(1,11) ]
    ref_printout = zip(xrange(1,11), [ "%.2f" % s for s in ref_results ])
    f = parallelized_function(func, max_children=2,
                              printout=cStringIO.StringIO())
    if 0:
      f.debug = True
      f.timeout = 0.1
    results = list(f(xrange(1,11)))
    if 0:
      print results
      print f.printout.getvalue()
    assert approx_equal(results, ref_results, eps=1e-3)
    matches = [ result_pat.search(li)
                for li in f.printout.getvalue().strip().split('\n') ]
    printout = [ (int(m.group(1)), m.group(2)) for m in matches ]
    printout.sort()
    assert printout == ref_printout
    sys.stdout.flush()
  except NotImplementedError:
    print "Skipped!"

  print "OK"

if __name__ == '__main__':
  exercise()
