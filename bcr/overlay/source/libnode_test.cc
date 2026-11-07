// SPDX-License-Identifier: MIT
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

#include "node.h"
#include "v8.h"

namespace {
void Require(bool condition, const char* message) {
  if (!condition) {
    std::fprintf(stderr, "check failed: patched libnode %s\n", message);
    std::exit(1);
  }
}

constexpr char kScript[] = R"JS(
const publicRequire = require('module').createRequire(process.cwd() + '/');
const assert = publicRequire('node:assert/strict');
const fs = publicRequire('node:fs');
const originalFs = publicRequire('original-fs');
const zlib = publicRequire('node:zlib');
const crypto = publicRequire('node:crypto');
const inspector = publicRequire('node:inspector');
assert.equal(process.versions.node, '22.20.0');
assert.equal(process.versions.modules, '140');
assert.notEqual(fs, originalFs);
assert.equal(publicRequire(publicRequire('node:path').resolve(process.argv[2])).answer, 42);
const fixture = 'source-built Electron Node fixture\n';
assert.equal(fs.readFileSync(process.argv[1], 'utf8'), fixture);
assert.equal(originalFs.readFileSync(process.argv[1], 'utf8'), fixture);
assert.equal(crypto.createHash('sha256').update('abc').digest('hex'),
  'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
const bytes = Buffer.from('captured Node compression payload\n'.repeat(64));
assert.deepEqual(zlib.brotliDecompressSync(zlib.brotliCompressSync(bytes)), bytes);
assert.deepEqual(zlib.zstdDecompressSync(zlib.zstdCompressSync(bytes)), bytes);
assert.throws(() => zlib.brotliDecompressSync(Buffer.from([0xff, 0xff])));
assert.throws(() => zlib.zstdDecompressSync(Buffer.from('invalid frame')));
const sqlite = publicRequire('node:sqlite');
const database = new sqlite.DatabaseSync(':memory:');
assert.equal(database.prepare('select 6 * 7 as answer').get().answer, 42);
database.close();
const session = new inspector.Session();
session.connect();
const evaluated = new Promise((resolve, reject) => {
  session.post('Runtime.evaluate', { expression: '6 * 7' }, (error, value) => {
    if (error) return reject(error);
    assert.equal(value.result.value, 42);
    session.disconnect();
    resolve();
  });
});
globalThis.probeDone = false;
Promise.all([fs.promises.readFile(process.argv[1], 'utf8'), evaluated])
  .then(([contents]) => { assert.equal(contents, fixture); globalThis.probeDone = true; });
)JS";
}  // namespace

int main(int argc, char** argv) {
  Require(argc == 5, "declared ICU, snapshot, fixture and addon arguments");
  Require(v8::V8::InitializeICUDefaultLocation(argv[0], argv[1]), "declared ICU data");
  v8::V8::InitializeExternalStartupDataFromFile(argv[2]);
  auto initialization = node::InitializeOncePerProcess({argv[0], argv[3], argv[4]}, {
      node::ProcessInitializationFlags::kNoInitializeV8,
      node::ProcessInitializationFlags::kNoInitializeNodeV8Platform,
      node::ProcessInitializationFlags::kNoDefaultSignalHandling,
  });
  Require(!initialization->early_return(), "process initialization");
  auto platform = node::MultiIsolatePlatform::Create(2);
  v8::V8::InitializePlatform(platform.get());
  Require(v8::V8::Initialize(), "V8 initialization");
  std::vector<std::string> errors;
  auto setup = node::CommonEnvironmentSetup::Create(
      platform.get(), &errors, initialization->args(), initialization->exec_args());
  Require(setup && errors.empty(), "environment creation");
  int exit_code = 1;
  {
    v8::Locker locker(setup->isolate());
    v8::Isolate::Scope isolate_scope(setup->isolate());
    v8::HandleScope handles(setup->isolate());
    auto context = setup->context();
    v8::Context::Scope context_scope(context);
    Require(!node::LoadEnvironment(setup->env(), kScript).IsEmpty(), "builtin module execution");
    exit_code = node::SpinEventLoop(setup->env()).FromMaybe(1);
    v8::Local<v8::Value> done;
    Require(context->Global()->Get(context, v8::String::NewFromUtf8Literal(setup->isolate(), "probeDone")).ToLocal(&done) && done->IsTrue(), "asynchronous filesystem and inspector completion");
  }
  setup.reset();
  v8::V8::Dispose();
  v8::V8::DisposePlatform();
  node::TearDownOncePerProcess();
  return exit_code;
}
