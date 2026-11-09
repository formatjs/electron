// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <fstream>
#include <memory>
#include <string>
#include <utility>

#include "base/at_exit.h"
#include "base/build_time.h"
#include "base/command_line.h"
#include "base/feature_list.h"
#include "base/functional/bind.h"
#include "base/functional/callback.h"
#include "base/files/file.h"
#include "base/files/file_util.h"
#include "base/files/memory_mapped_file.h"
#include "base/files/scoped_temp_dir.h"
#include "base/i18n/icu_util.h"
#include "base/run_loop.h"
#include "base/strings/string_number_conversions.h"
#include "base/task/single_thread_task_executor.h"
#include "base/task/thread_pool.h"
#include "base/task/thread_pool/thread_pool_instance.h"
#include "base/threading/thread.h"
#include "base/time/time_override.h"
#include "components/services/storage/dom_storage/dom_storage_database.h"
#include "crypto/nss_util.h"
#include "crypto/sha2.h"
#include "mojo/core/embedder/embedder.h"
#include "mojo/core/embedder/scoped_ipc_support.h"
#include "mojo/public/c/system/buffer.h"
#include "mojo/public/c/system/data_pipe.h"
#include "mojo/public/c/system/functions.h"
#include "mojo/public/c/system/message_pipe.h"
#include "net/base/registry_controlled_domains/registry_controlled_domain.h"
#include "net/http/transport_security_state.h"
#include "nss.h"
#include "pk11pub.h"
#include "lib/freebl/loader.h"
#include "sql/database.h"
#include "sql/statement.h"
#include "third_party/leveldatabase/env_chromium.h"
#include "third_party/leveldatabase/src/include/leveldb/db.h"
#include "url/gurl.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: network %s\n", message);
    std::exit(1);
  }
}
void Stage(const char* name) {
  std::fprintf(stderr, "network probe stage: %s\n", name);
}

base::Time TimelyBuildTime() { return base::GetBuildTime() + base::Days(69); }
base::Time ExpiredBuildTime() { return base::GetBuildTime() + base::Days(70); }

void CheckLeveldb() {
  base::ScopedTempDir directory;
  Require(directory.CreateUniqueTempDir(), "LevelDB temporary directory");
  const auto path = directory.GetPath().Append(
      base::FilePath::FromUTF8Unsafe("database with spaces \xe4\xb8\x96\xe7\x95\x8c"));
  Require(path.IsAbsolute(), "LevelDB absolute database path");
  const auto name = path.AsUTF8Unsafe();
  leveldb_env::ChromiumEnv environment;
  leveldb_env::Options options;
  options.env = &environment;
  options.create_if_missing = true;
  std::unique_ptr<leveldb::DB> database;
  Require(leveldb_env::OpenDB(options, name, &database).ok(), "LevelDB persistent open");
  const std::string key("key\0bytes", 9);
  const std::string expected("value\0bytes", 11);
  leveldb::WriteOptions write;
  write.sync = true;
  Require(database->Put(write, key, expected).ok(), "LevelDB persistent write");
  database.reset();
  options.create_if_missing = false;
  Require(leveldb_env::OpenDB(options, name, &database).ok(), "LevelDB persistent reopen");
  std::string value;
  Require(database->Get(leveldb::ReadOptions(), key, &value).ok() && value == expected,
          "LevelDB persisted binary value");
  database.reset();
  Require(leveldb::DestroyDB(name, options).ok() && !base::PathExists(path),
          "LevelDB persistent destroy");
  options.create_if_missing = true;
  Require(leveldb_env::OpenDB(options, name, &database).ok(), "LevelDB persistent open");
  database.reset();
  base::RunLoop loop;
  storage::DomStorageDatabaseFactory::Destroy(
      directory.GetPath(), path.BaseName().AsUTF8Unsafe(),
      base::ThreadPool::CreateSequencedTaskRunner(
          {base::MayBlock(), base::WithBaseSyncPrimitives(),
           base::TaskShutdownBehavior::BLOCK_SHUTDOWN}),
      base::BindOnce(
          [](base::RepeatingClosure quit, storage::DbStatus status) {
            Require(status.ok(), "DOM storage persistent destroy");
            quit.Run();
          },
          loop.QuitClosure()));
  loop.Run();
  Require(!base::PathExists(path), "DOM storage persistent destroy");
}

void CheckNetwork() {
  const GURL url("https://b\xc3\xbc" "cher.example:443/a/../b?q=x#f");
  Require(url.is_valid() && url.spec() == "https://xn--bcher-kva.example/b?q=x#f", "IDNA and URL canonicalization");
  Require(!GURL("https://[invalid/").is_valid(), "invalid URL rejected");
  Require(net::registry_controlled_domains::GetDomainAndRegistry(GURL("https://a.example.co.uk"), net::registry_controlled_domains::INCLUDE_PRIVATE_REGISTRIES) == "example.co.uk", "generated public suffix lookup");
  net::TransportSecurityState security;
  net::TransportSecurityState::STSState state;
  {
    base::subtle::ScopedTimeClockOverrides clock(&TimelyBuildTime, nullptr, nullptr);
    Require(security.GetStaticSTSState("example.dev", &state) && state.ShouldUpgradeToSSL(), "generated HSTS preload lookup");
    Require(!security.GetStaticSTSState("invalid.test", &state), "non-preloaded domain rejected");
  }
  {
    base::subtle::ScopedTimeClockOverrides clock(&ExpiredBuildTime, nullptr, nullptr);
    Require(!security.GetStaticSTSState("example.dev", &state), "expired HSTS preload rejected");
  }
  const auto hash = crypto::SHA256HashString("abc");
  Require(base::HexEncode(hash.data(), hash.size()) == "BA7816BF8F01CFEA414140DE5DAE2223B00361A396177A9CB410FF61F20015AD", "native crypto hash vector");
  crypto::EnsureNSSInit();
  Require(std::string(NSS_GetVersion()).starts_with("3.61"), "source-built NSS version");
  unsigned char random[32];
  Require(PK11_GenerateRandom(random, sizeof(random)) == SECSuccess, "source-built NSS random generation");
  sql::Database database("Test");
  Require(database.OpenInMemory(), "Chromium SQL memory database");
  Require(database.Execute("CREATE TABLE values_table(value INTEGER)"), "Chromium SQL schema creation");
  Require(database.Execute("INSERT INTO values_table VALUES(19), (23)"), "Chromium SQL insertion");
  sql::Statement statement(database.GetUniqueStatement("SELECT sum(value) FROM values_table"));
  Require(statement.Step() && statement.ColumnInt(0) == 42 && !statement.Step() && statement.Succeeded(), "Chromium SQL query and completion");
}

void CheckMojo() {
  MojoHandle sender, receiver;
  Require(MojoCreateMessagePipe(nullptr, &sender, &receiver) == MOJO_RESULT_OK, "native message pipe creation");
  std::string payload(65537, 'm');
  payload.front() = '\0';
  payload.back() = '\x7f';
  MojoMessageHandle message;
  Require(MojoCreateMessage(nullptr, &message) == MOJO_RESULT_OK, "native message creation");
  MojoAppendMessageDataOptions append{sizeof(append), MOJO_APPEND_MESSAGE_DATA_FLAG_COMMIT_SIZE};
  void* bytes;
  uint32_t size;
  Require(MojoAppendMessageData(message, payload.size(), nullptr, 0, &append, &bytes, &size) == MOJO_RESULT_OK && size >= payload.size(), "native message payload allocation");
  std::memcpy(bytes, payload.data(), payload.size());
  Require(MojoWriteMessage(sender, message, nullptr) == MOJO_RESULT_OK, "native message write");
  Require(MojoReadMessage(receiver, nullptr, &message) == MOJO_RESULT_OK, "native message read");
  Require(MojoGetMessageData(message, nullptr, &bytes, &size, nullptr, nullptr) == MOJO_RESULT_OK && std::string(static_cast<char*>(bytes), size) == payload, "binary message payload retained");
  Require(MojoDestroyMessage(message) == MOJO_RESULT_OK, "native message cleanup");
  Require(MojoReadMessage(receiver, nullptr, &message) == MOJO_RESULT_SHOULD_WAIT, "empty message pipe waits");
  Require(MojoClose(sender) == MOJO_RESULT_OK && MojoReadMessage(receiver, nullptr, &message) == MOJO_RESULT_FAILED_PRECONDITION && MojoClose(receiver) == MOJO_RESULT_OK, "message peer closure and cleanup");

  MojoHandle producer, consumer;
  Require(MojoCreateDataPipe(nullptr, &producer, &consumer) == MOJO_RESULT_OK, "native data pipe creation");
  const char data[] = "data\0pipe";
  size = sizeof(data);
  Require(MojoWriteData(producer, data, &size, nullptr) == MOJO_RESULT_OK && size == sizeof(data), "native data pipe write");
  char received[sizeof(data)];
  size = sizeof(received);
  Require(MojoReadData(consumer, nullptr, received, &size) == MOJO_RESULT_OK && size == sizeof(data) && std::memcmp(data, received, size) == 0, "native data pipe binary read");
  Require(MojoClose(producer) == MOJO_RESULT_OK && MojoClose(consumer) == MOJO_RESULT_OK, "data pipe cleanup");

  MojoHandle buffer, duplicate;
  Require(MojoCreateSharedBuffer(4096, nullptr, &buffer) == MOJO_RESULT_OK && MojoDuplicateBufferHandle(buffer, nullptr, &duplicate) == MOJO_RESULT_OK, "shared buffer creation and duplication");
  void *original, *copy;
  Require(MojoMapBuffer(buffer, 0, 4096, nullptr, &original) == MOJO_RESULT_OK && MojoMapBuffer(duplicate, 0, 4096, nullptr, &copy) == MOJO_RESULT_OK, "shared buffer mappings");
  std::memcpy(original, data, sizeof(data));
  Require(std::memcmp(copy, data, sizeof(data)) == 0, "shared buffer coherence");
  Require(MojoUnmapBuffer(original) == MOJO_RESULT_OK && MojoUnmapBuffer(copy) == MOJO_RESULT_OK && MojoClose(buffer) == MOJO_RESULT_OK && MojoClose(duplicate) == MOJO_RESULT_OK, "shared buffer cleanup");
  Require(MojoClose(MOJO_HANDLE_INVALID) == MOJO_RESULT_INVALID_ARGUMENT, "invalid Mojo handle rejected");
}

void CheckIntegrity(const char* module_argument, const char* checksum_argument) {
  const auto module = base::MakeAbsoluteFilePath(base::FilePath(module_argument));
  const auto checksum = base::MakeAbsoluteFilePath(base::FilePath(checksum_argument));
  Require(!module.empty() && !checksum.empty(), "declared NSS integrity files");
  void* library = dlopen(module.value().c_str(), RTLD_NOW | RTLD_LOCAL);
  Require(library != nullptr, "declared NSS implementation load");
  auto get_vector = reinterpret_cast<FREEBLGetVectorFn*>(dlsym(library, "FREEBL_GetVector"));
  Require(get_vector != nullptr, "original NSS vector entry point");
  const auto* vector = get_vector();
  Require(vector && vector->p_BLAPI_SHVerifyFile(module.value().c_str()), "original NSS accepts generated integrity");
  base::ScopedTempDir temporary;
  Require(temporary.CreateUniqueTempDir(), "NSS integrity temporary directory");
  const auto copied = temporary.GetPath().AppendASCII("module.so");
  const auto copied_checksum = temporary.GetPath().AppendASCII("module.chk");
  Require(base::CopyFile(module, copied) && base::CopyFile(checksum, copied_checksum), "NSS integrity file relocation");
  Require(vector->p_BLAPI_SHVerifyFile(copied.value().c_str()), "original NSS accepts relocated integrity");
  {
    std::fstream file(copied.value(), std::ios::in | std::ios::out | std::ios::binary);
    file.seekg(-1, std::ios::end);
    char byte;
    file.read(&byte, 1);
    byte ^= 1;
    file.seekp(-1, std::ios::end);
    file.write(&byte, 1);
    Require(file.good(), "NSS corruption fixture write");
  }
  Require(!vector->p_BLAPI_SHVerifyFile(copied.value().c_str()), "original NSS rejects corrupt module");
  Require(base::CopyFile(module, copied), "NSS module fixture restoration");
  {
    std::fstream file(copied_checksum.value(), std::ios::in | std::ios::out | std::ios::binary);
    file.seekg(-1, std::ios::end);
    char byte;
    file.read(&byte, 1);
    byte ^= 1;
    file.seekp(-1, std::ios::end);
    file.write(&byte, 1);
    Require(file.good(), "NSS signature fixture write");
  }
  Require(!vector->p_BLAPI_SHVerifyFile(copied.value().c_str()), "original NSS rejects corrupt integrity");
  Require(dlclose(library) == 0, "NSS integrity library cleanup");
}
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 4, "declared ICU and NSS integrity arguments");
  base::AtExitManager at_exit;
  base::CommandLine::Init(argc, argv);
  Require(base::FeatureList::InitInstance("", ""), "default feature initialization");
  base::SingleThreadTaskExecutor executor;
  base::ThreadPoolInstance::CreateAndStartWithDefaultParams("source-network");
  Stage("icu");
  base::File data(base::MakeAbsoluteFilePath(base::FilePath(argv[1])), base::File::FLAG_OPEN | base::File::FLAG_READ);
  Require(data.IsValid() && base::i18n::InitializeICUWithFileDescriptor(data.TakePlatformFile(), base::MemoryMappedFile::Region::kWholeFile), "declared ICU initialization");
  Stage("modules");
  CheckNetwork();
  CheckLeveldb();
  Stage("integrity");
  CheckIntegrity(argv[2], argv[3]);
  Stage("platform");
  base::Thread thread("mojo-io");
  base::Thread::Options options;
  options.message_pump_type = base::MessagePumpType::IO;
  Require(thread.StartWithOptions(std::move(options)), "Mojo IO thread initialization");
  mojo::core::Configuration configuration;
  configuration.is_broker_process = true;
  mojo::core::Init(configuration);
  Require(mojo::core::IsMojoIpczEnabled(), "original IPCz configuration enabled");
  {
    mojo::core::ScopedIPCSupport support(thread.task_runner(), mojo::core::ScopedIPCSupport::ShutdownPolicy::CLEAN);
    Stage("callback");
    CheckMojo();
    Stage("shutdown");
  }
  mojo::core::ShutDown();
  thread.Stop();
  base::ThreadPoolInstance::Get()->Shutdown();
  base::i18n::ResetGlobalsForTesting();
  Stage("done");
}
