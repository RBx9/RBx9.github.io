#!/usr/bin/env python3
# RBx9 Signer 1.3.24 private: failed downloads now say why.
#  - A download that fails after all retries shows an alert with the reason,
#    instead of silently returning the button to "Get".
#  - An error while handling the finished file (bad IPA, no space) is shown too.
# Apply AFTER upgrade_v1_3_23_stages.py. Set RBX9_TREE to use another tree.
import os
from pathlib import Path

tree = Path(os.environ.get("RBX9_TREE", "feather"))
p = tree / "Feather/Backend/Observable/DownloadManager.swift"
s = p.read_text()


def once(old, new, label):
    global s
    assert s.count(old) == 1, ("v1.3.24 " + label, s.count(old))
    s = s.replace(old, new, 1)


once(r'''			print("Error handling downloaded file: \(error.localizedDescription)")
''', r'''			print("Error handling downloaded file: \(error.localizedDescription)")
			let name = download.fileName
			DispatchQueue.main.async {
				self._rbx9ForgetProvenance(id: download.id)
				if let index = self.getDownloadIndex(by: download.id) {
					self.downloads.remove(at: index)
				}
				UIAlertController.showAlertWithOk(
					title: "Download failed",
					message: "\(name) downloaded but could not be processed. \(error.localizedDescription)"
				)
			}
''', "finish error")

once(r'''		DispatchQueue.main.async {
			self._rbx9ForgetProvenance(id: download.id)
			if let index = self.getDownloadIndex(by: download.id) {
				self.downloads.remove(at: index)
			}
		}
	}

	/// iOS has delivered every event queued''', r'''		let failedName = download.fileName
		let failedHost = download.task?.originalRequest?.url?.host ?? "the server"
		DispatchQueue.main.async {
			self._rbx9ForgetProvenance(id: download.id)
			if let index = self.getDownloadIndex(by: download.id) {
				self.downloads.remove(at: index)
			}
			if nsError.code != NSURLErrorCancelled {
				UIAlertController.showAlertWithOk(
					title: "Download failed",
					message: "\(failedName) could not be downloaded from \(failedHost). \(error.localizedDescription) (code \(nsError.code))"
				)
			}
		}
	}

	/// iOS has delivered every event queued''', "final failure")

p.write_text(s)

cfg = tree / "Feather.xcconfig"
c = cfg.read_text()
if c.count("FEATHER_PROJECT_VERSION=1.3.23") != 1:
    raise RuntimeError("v1.3.24: expected base 1.3.23")
cfg.write_text(c.replace("FEATHER_PROJECT_VERSION=1.3.23", "FEATHER_PROJECT_VERSION=1.3.24", 1))
print("RBx9 v1.3.24 private: download failures are reported")
