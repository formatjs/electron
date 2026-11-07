// SPDX-License-Identifier: MIT
#include <atomic>
#include <cmath>
#include <memory>

#include "src/base/ieee754.h"
#include "src/base/platform/semaphore.h"
#include "src/base/platform/time.h"
#include "src/libplatform/default-foreground-task-runner.h"
#include "src/libplatform/default-worker-threads-task-runner.h"

namespace {
double Clock() {
  return v8::base::TimeTicks::Now().ToInternalValue() / 1000000.0;
}

double foreground_time = 0;
double ForegroundClock() { return foreground_time; }

class CountTask final : public v8::Task {
 public:
  CountTask(std::atomic<int>& count, v8::base::Semaphore& done)
      : count_(count), done_(done) {}
  void Run() override {
    ++count_;
    done_.Signal();
  }
 private:
  std::atomic<int>& count_;
  v8::base::Semaphore& done_;
};
}

int main() {
  if (std::abs(v8::base::ieee754::libm_sin(0.5) - 0.4794255386042030) > 1e-15 ||
      std::abs(v8::base::ieee754::libm_cos(0.5) - 0.8775825618903727) > 1e-15) return 7;
  std::atomic<int> count{0};
  v8::base::Semaphore done(0);
  v8::platform::DefaultWorkerThreadsTaskRunner worker(2, Clock);
  for (int index = 0; index < 32; ++index) {
    worker.PostTask(std::make_unique<CountTask>(count, done));
  }
  worker.PostDelayedTask(std::make_unique<CountTask>(count, done), 0.002);
  for (int index = 0; index < 33; ++index) {
    if (!done.WaitFor(v8::base::TimeDelta::FromSeconds(2))) {
      worker.Terminate();
      return 1;
    }
  }
  worker.Terminate();
  worker.PostTask(std::make_unique<CountTask>(count, done));
  if (count != 33) return 2;

  auto foreground = std::make_shared<v8::platform::DefaultForegroundTaskRunner>(
      v8::platform::IdleTaskSupport::kDisabled, ForegroundClock);
  foreground->PostTask(std::make_unique<CountTask>(count, done));
  foreground->PostDelayedTask(std::make_unique<CountTask>(count, done), 1);
  auto immediate = foreground->PopTaskFromQueue(v8::platform::MessageLoopBehavior::kDoNotWait);
  if (!immediate) return 3;
  immediate->Run();
  if (foreground->PopTaskFromQueue(v8::platform::MessageLoopBehavior::kDoNotWait)) return 4;
  foreground_time = 2;
  auto delayed = foreground->PopTaskFromQueue(v8::platform::MessageLoopBehavior::kDoNotWait);
  if (!delayed) return 5;
  delayed->Run();
  foreground->Terminate();
  return count == 35 ? 0 : 6;
}
