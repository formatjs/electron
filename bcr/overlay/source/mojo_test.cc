#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <utility>
#include <vector>

#include "base/at_exit.h"
#include "base/command_line.h"
#include "base/feature_list.h"
#include "base/process/launch.h"
#include "base/process/process.h"
#include "base/run_loop.h"
#include "base/task/single_thread_task_executor.h"
#include "base/threading/thread.h"
#include "base/time/time.h"
#include "mojo/core/embedder/embedder.h"
#include "mojo/core/embedder/scoped_ipc_support.h"
#include "mojo/public/c/system/buffer.h"
#include "mojo/public/c/system/data_pipe.h"
#include "mojo/public/c/system/functions.h"
#include "mojo/public/c/system/message_pipe.h"
#include "mojo/public/cpp/bindings/receiver.h"
#include "mojo/public/cpp/bindings/remote.h"
#include "mojo/public/cpp/platform/platform_channel.h"
#include "mojo/public/cpp/system/invitation.h"
#include "mojo/public/cpp/system/message_pipe.h"
#include "mojo/public/cpp/system/wait.h"
#include "services/service_manager/public/mojom/interface_provider.mojom.h"

void Check(bool value, const char* message) {
  if (!value) {
    std::cerr << "check failed: mojo " << message << '\n';
    std::exit(1);
  }
}

void CheckResult(MojoResult actual, MojoResult expected, const char* call) {
  if (actual != expected) {
    std::cerr << "check failed: mojo result " << call << ": got " << actual << ", expected " << expected
              << '\n';
    std::exit(1);
  }
}

#define RESULT(call, expected) CheckResult((call), (expected), #call)

class Provider : public service_manager::mojom::InterfaceProvider {
 public:
  Provider(
      mojo::PendingReceiver<service_manager::mojom::InterfaceProvider> pending,
      base::OnceClosure done)
      : receiver(this, std::move(pending)), done_(std::move(done)) {}

  void GetInterface(const std::string& name,
                    mojo::ScopedMessagePipeHandle pipe) override {
    Check(name == std::string("native\0interface", 16), "typed string changed");
    RESULT(mojo::WriteMessageRaw(pipe.get(), "bound", 5, nullptr, 0, 0),
           MOJO_RESULT_OK);
    ++calls;
    Check(static_cast<bool>(done_), "unexpected typed dispatch");
    std::move(done_).Run();
  }

  mojo::Receiver<service_manager::mojom::InterfaceProvider> receiver;
  int calls = 0;

 private:
  base::OnceClosure done_;
};

void RejectMalformedMessage() {
  mojo::MessagePipe pipe;
  base::RunLoop loop;
  Provider provider(
      mojo::PendingReceiver<service_manager::mojom::InterfaceProvider>(
          std::move(pipe.handle1)),
      {});
  provider.receiver.set_disconnect_handler(loop.QuitClosure());
  RESULT(mojo::WriteMessageRaw(pipe.handle0.get(), "bad", 3, nullptr, 0, 0),
         MOJO_RESULT_OK);
  loop.Run();
  Check(provider.calls == 0, "malformed message dispatched");
}

int Child() {
  auto invitation = mojo::IncomingInvitation::Accept(
      mojo::PlatformChannel::RecoverPassedEndpointFromCommandLine(
          *base::CommandLine::ForCurrentProcess()));
  auto pipe = invitation.ExtractMessagePipe(uint64_t{0});
  Check(pipe.is_valid(), "child invitation missing pipe");
  RESULT(mojo::Wait(pipe.get(), MOJO_HANDLE_SIGNAL_READABLE), MOJO_RESULT_OK);
  std::vector<uint8_t> bytes;
  std::vector<mojo::ScopedHandle> handles;
  RESULT(mojo::ReadMessageRaw(pipe.get(), &bytes, &handles, 0), MOJO_RESULT_OK);
  std::string expected(65537, 'p');
  expected.front() = 0;
  expected.back() = 127;
  Check(std::string(bytes.begin(), bytes.end()) == expected,
        "cross-process payload changed");
  Check(handles.size() == 1, "child shared buffer missing");
  void* memory;
  RESULT(MojoMapBuffer(handles[0].get().value(), 0, 4096, nullptr, &memory),
         MOJO_RESULT_OK);
  Check(std::memcmp(memory, "process\0shared", 15) == 0,
        "child shared bytes changed");
  static_cast<char*>(memory)[0] = 'X';
  RESULT(MojoUnmapBuffer(memory), MOJO_RESULT_OK);
  RESULT(mojo::WriteMessageRaw(pipe.get(), "ack", 3, nullptr, 0, 0),
         MOJO_RESULT_OK);
  base::RunLoop loop;
  Provider provider(
      mojo::PendingReceiver<service_manager::mojom::InterfaceProvider>(
          invitation.ExtractMessagePipe(uint64_t{1})),
      loop.QuitClosure());
  loop.Run();
  Check(provider.calls == 1, "typed request not dispatched");
  RESULT(mojo::Wait(pipe.get(), MOJO_HANDLE_SIGNAL_READABLE), MOJO_RESULT_OK);
  RESULT(mojo::ReadMessageRaw(pipe.get(), &bytes, &handles, 0), MOJO_RESULT_OK);
  Check(std::string(bytes.begin(), bytes.end()) == "done",
        "parent completion missing");
  return 0;
}

void ProcessTransfer() {
  mojo::PlatformChannel channel;
  base::CommandLine command(
      base::CommandLine::ForCurrentProcess()->GetProgram());
  command.AppendSwitch("mojo-child");
  base::LaunchOptions options;
  channel.PrepareToPassRemoteEndpoint(&options, &command);
  auto process = base::LaunchProcess(command, options);
  channel.RemoteProcessLaunchAttempted();
  Check(process.IsValid(), "child launch failed");
  mojo::OutgoingInvitation invitation;
  auto pipe = invitation.AttachMessagePipe(uint64_t{0});
  auto binding_pipe = invitation.AttachMessagePipe(uint64_t{1});
  mojo::OutgoingInvitation::Send(std::move(invitation), process.Handle(),
                                 channel.TakeLocalEndpoint());
  MojoHandle buffer;
  RESULT(MojoCreateSharedBuffer(4096, nullptr, &buffer), MOJO_RESULT_OK);
  void* memory;
  RESULT(MojoMapBuffer(buffer, 0, 4096, nullptr, &memory), MOJO_RESULT_OK);
  std::memcpy(memory, "process\0shared", 15);
  std::string payload(65537, 'p');
  payload.front() = 0;
  payload.back() = 127;
  RESULT(mojo::WriteMessageRaw(pipe.get(), payload.data(), payload.size(),
                               &buffer, 1, 0),
         MOJO_RESULT_OK);
  RESULT(mojo::Wait(pipe.get(), MOJO_HANDLE_SIGNAL_READABLE), MOJO_RESULT_OK);
  std::vector<uint8_t> received;
  std::vector<mojo::ScopedHandle> handles;
  RESULT(mojo::ReadMessageRaw(pipe.get(), &received, &handles, 0),
         MOJO_RESULT_OK);
  Check(std::string(received.begin(), received.end()) == "ack",
        "child reply missing");
  Check(static_cast<char*>(memory)[0] == 'X',
        "cross-process mapping lost coherence");
  RESULT(MojoUnmapBuffer(memory), MOJO_RESULT_OK);
  mojo::Remote<service_manager::mojom::InterfaceProvider> remote(
      mojo::PendingRemote<service_manager::mojom::InterfaceProvider>(
          std::move(binding_pipe), 0));
  mojo::MessagePipe reply;
  remote->GetInterface(std::string("native\0interface", 16),
                       std::move(reply.handle1));
  RESULT(mojo::Wait(reply.handle0.get(), MOJO_HANDLE_SIGNAL_READABLE),
         MOJO_RESULT_OK);
  RESULT(mojo::ReadMessageRaw(reply.handle0.get(), &received, &handles, 0),
         MOJO_RESULT_OK);
  Check(std::string(received.begin(), received.end()) == "bound",
        "typed reply missing");
  RESULT(mojo::WriteMessageRaw(pipe.get(), "done", 4, nullptr, 0, 0),
         MOJO_RESULT_OK);
  int exit_code;
  Check(process.WaitForExitWithTimeout(base::Seconds(10), &exit_code) &&
            exit_code == 0,
        "child failed to exit cleanly");
}

int main(int argc, char** argv) {
  base::AtExitManager at_exit;
  base::CommandLine::Init(argc, argv);
  base::FeatureList::InitInstance("", "");
  base::SingleThreadTaskExecutor main_executor;
  base::Thread ipc_thread("mojo-io");
  base::Thread::Options options;
  options.message_pump_type = base::MessagePumpType::IO;
  Check(ipc_thread.StartWithOptions(std::move(options)), "IPC thread failed");
  mojo::core::Configuration configuration;
  const bool child =
      base::CommandLine::ForCurrentProcess()->HasSwitch("mojo-child");
  configuration.is_broker_process = !child;
  mojo::core::Init(configuration);
  Check(mojo::core::IsMojoIpczEnabled(), "ipcz core not selected");
  mojo::core::ScopedIPCSupport support(
      ipc_thread.task_runner(),
      mojo::core::ScopedIPCSupport::ShutdownPolicy::CLEAN);
  if (child)
    return Child();

  mojo::ScopedMessagePipeHandle sender, receiver;
  RESULT(mojo::CreateMessagePipe(nullptr, &sender, &receiver), MOJO_RESULT_OK);
  std::string payload(65537, 'm');
  payload.front() = '\0';
  payload.back() = '\x7f';
  RESULT(mojo::WriteMessageRaw(sender.get(), payload.data(), payload.size(),
                               nullptr, 0, 0),
         MOJO_RESULT_OK);
  std::vector<uint8_t> received;
  std::vector<mojo::ScopedHandle> handles;
  RESULT(mojo::ReadMessageRaw(receiver.get(), &received, &handles, 0),
         MOJO_RESULT_OK);
  Check(std::string(received.begin(), received.end()) == payload,
        "message bytes changed");
  Check(handles.empty(), "unexpected attached handles");
  RESULT(mojo::ReadMessageRaw(receiver.get(), &received, &handles, 0),
         MOJO_RESULT_SHOULD_WAIT);

  MojoHandle buffer;
  RESULT(MojoCreateSharedBuffer(4096, nullptr, &buffer), MOJO_RESULT_OK);
  void* original;
  RESULT(MojoMapBuffer(buffer, 0, 4096, nullptr, &original), MOJO_RESULT_OK);
  std::memcpy(original, "shared\0bytes", 12);
  void* invalid_mapping;
  RESULT(MojoMapBuffer(buffer, 4096, 1, nullptr, &invalid_mapping),
         MOJO_RESULT_RESOURCE_EXHAUSTED);
  RESULT(mojo::WriteMessageRaw(sender.get(), "b", 1, &buffer, 1, 0),
         MOJO_RESULT_OK);
  RESULT(mojo::ReadMessageRaw(receiver.get(), &received, &handles, 0),
         MOJO_RESULT_OK);
  Check(handles.size() == 1, "shared buffer handle lost");
  void* transferred;
  RESULT(
      MojoMapBuffer(handles[0].get().value(), 0, 4096, nullptr, &transferred),
      MOJO_RESULT_OK);
  Check(std::memcmp(original, transferred, 12) == 0,
        "shared buffer bytes changed");
  static_cast<char*>(transferred)[1] = 'X';
  Check(static_cast<char*>(original)[1] == 'X',
        "shared mapping lost coherence");
  RESULT(MojoUnmapBuffer(transferred), MOJO_RESULT_OK);
  RESULT(MojoUnmapBuffer(original), MOJO_RESULT_OK);
  handles.clear();

  MojoHandle producer, consumer;
  MojoCreateDataPipeOptions data_options = {
      .struct_size = sizeof(data_options),
      .flags = MOJO_CREATE_DATA_PIPE_FLAG_NONE,
      .element_num_bytes = 1,
      .capacity_num_bytes = 32};
  RESULT(MojoCreateDataPipe(&data_options, &producer, &consumer),
         MOJO_RESULT_OK);
  uint32_t bytes = 12;
  RESULT(MojoWriteData(producer, "data\0payload", &bytes, nullptr),
         MOJO_RESULT_OK);
  char data[32];
  bytes = sizeof(data);
  RESULT(MojoReadData(consumer, nullptr, data, &bytes), MOJO_RESULT_OK);
  Check(bytes == 12 && std::memcmp(data, "data\0payload", 12) == 0,
        "data pipe bytes changed");
  bytes = sizeof(data);
  RESULT(MojoReadData(consumer, nullptr, data, &bytes),
         MOJO_RESULT_SHOULD_WAIT);
  RESULT(MojoClose(producer), MOJO_RESULT_OK);
  RESULT(MojoReadData(consumer, nullptr, data, &bytes),
         MOJO_RESULT_FAILED_PRECONDITION);
  RESULT(MojoClose(consumer), MOJO_RESULT_OK);
  receiver.reset();
  MojoHandleSignalsState state;
  RESULT(MojoQueryHandleSignalsState(sender.get().value(), &state),
         MOJO_RESULT_OK);
  Check(state.satisfied_signals & MOJO_HANDLE_SIGNAL_PEER_CLOSED,
        "peer closure missing");
  RESULT(MojoClose(MOJO_HANDLE_INVALID), MOJO_RESULT_INVALID_ARGUMENT);
  ProcessTransfer();
  RejectMalformedMessage();
}
