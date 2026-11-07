// SPDX-License-Identifier: MIT
#include <cstdlib>
#include <iostream>
#include <string>
#include <vector>

#include "third_party/ipcz/include/ipcz/ipcz.h"
#include "third_party/ipcz/src/api.h"
#include "reference_drivers/sync_reference_driver.h"

void Check(bool value, const char* message) {
  if (!value) {
    std::cerr << "check failed: ipcz " << message << '\n';
    std::exit(1);
  }
}

#define RESULT(call, expected) Check((call) == (expected), #call)

int main() {
  std::cerr << "ipcz probe stage: platform\n";
  IpczAPI invalid = {};
  RESULT(IpczGetAPI(&invalid), IPCZ_RESULT_INVALID_ARGUMENT);
  IpczAPI api = {.size = sizeof(api)};
  RESULT(IpczGetAPI(&api), IPCZ_RESULT_OK);
  RESULT(api.Close(IPCZ_INVALID_HANDLE, 0, nullptr), IPCZ_RESULT_INVALID_ARGUMENT);
  const auto& driver = ipcz::reference_drivers::kSyncReferenceDriver;
  IpczHandle broker, client;
  RESULT(api.CreateNode(&driver, IPCZ_CREATE_NODE_AS_BROKER, nullptr, &broker), IPCZ_RESULT_OK);
  RESULT(api.CreateNode(&driver, 0, nullptr, &client), IPCZ_RESULT_OK);
  IpczDriverHandle transport0, transport1;
  RESULT(driver.CreateTransports(IPCZ_INVALID_DRIVER_HANDLE, IPCZ_INVALID_DRIVER_HANDLE,
                                 0, nullptr, &transport0, &transport1), IPCZ_RESULT_OK);
  IpczHandle a, b;
  RESULT(api.ConnectNode(broker, transport0, 1, 0, nullptr, &a), IPCZ_RESULT_OK);
  RESULT(api.ConnectNode(client, transport1, 1, IPCZ_CONNECT_NODE_TO_BROKER, nullptr, &b), IPCZ_RESULT_OK);

  std::cerr << "ipcz probe stage: modules\n";
  std::string payload(65537, 'x');
  payload.front() = '\0';
  payload.back() = '\x7f';
  RESULT(api.Put(a, payload.data(), payload.size(), nullptr, 0, 0, nullptr), IPCZ_RESULT_OK);
  char small;
  size_t bytes = 1;
  RESULT(api.Get(b, 0, nullptr, &small, &bytes, nullptr, nullptr, nullptr), IPCZ_RESULT_RESOURCE_EXHAUSTED);
  Check(bytes == payload.size(), "capacity failure lost required size");
  std::vector<char> received(bytes);
  RESULT(api.Get(b, 0, nullptr, received.data(), &bytes, nullptr, nullptr, nullptr), IPCZ_RESULT_OK);
  Check(std::string(received.data(), bytes) == payload, "binary payload changed");

  std::cerr << "ipcz probe stage: callback\n";
  IpczHandle local, transferred;
  RESULT(api.OpenPortals(broker, 0, nullptr, &local, &transferred), IPCZ_RESULT_OK);
  RESULT(api.Put(a, nullptr, 0, &transferred, 1, 0, nullptr), IPCZ_RESULT_OK);
  IpczHandle remote;
  size_t handles = 1;
  RESULT(api.Get(b, 0, nullptr, nullptr, nullptr, &remote, &handles, nullptr), IPCZ_RESULT_OK);
  Check(handles == 1, "portal transfer lost handle");
  const std::string message = "transferred portal";
  RESULT(api.Put(local, message.data(), message.size(), nullptr, 0, 0, nullptr), IPCZ_RESULT_OK);
  received.resize(message.size());
  bytes = received.size();
  RESULT(api.Get(remote, 0, nullptr, received.data(), &bytes, nullptr, nullptr, nullptr), IPCZ_RESULT_OK);
  Check(std::string(received.data(), bytes) == message, "transferred portal failed");
  RESULT(api.Close(remote, 0, nullptr), IPCZ_RESULT_OK);
  IpczPortalStatus status = {.size = sizeof(status)};
  RESULT(api.QueryPortalStatus(local, 0, nullptr, &status), IPCZ_RESULT_OK);
  Check(status.flags & IPCZ_PORTAL_STATUS_PEER_CLOSED, "peer closure not delivered");
  std::cerr << "ipcz probe stage: shutdown\n";
  for (IpczHandle handle : {local, a, b, client, broker}) {
    RESULT(api.Close(handle, 0, nullptr), IPCZ_RESULT_OK);
  }
  std::cerr << "ipcz probe stage: done\n";
}
