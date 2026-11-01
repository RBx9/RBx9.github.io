# RBx9 Source Manager

A native SwiftUI manager for RBx9's ESign/Feather source and Sileo tweak source.

- ESign: list, edit, remove catalog apps; upload IPA via draft GitHub Release asset, then publish.
- Sileo: list, remove DEB entries; upload a DEB, compute SHA-256 and append the verified release URL to `package-sources.txt`.
- Settings: GitHub authorization through an OAuth App **Device Flow** (requires your own OAuth Client ID with device flow enabled), or a fine-grained GitHub token kept in iOS Keychain. Icons and source metadata can be changed independently.
- Repo: `RBx9/RBx9.github.io` (requires permissions to write that repo).
- Source updates trigger the existing GitHub Actions publishers and go live when Pages publishes; clients may need to refresh.

## Sign in
To use GitHub Device Flow, register a GitHub OAuth App, enable Device Flow, put its public Client ID in the app Settings, and authorize via github.com/login/device. A Client ID is *not* a secret; never embed GitHub access tokens in your app.

Alternatively, in Settings, paste a **fine-grained personal access token** with Contents: Read and write for **RBx9/RBx9.github.io**. Repository token is stored in iOS Keychain. The app never uses your GitHub password.

## Build
Workflow `build-source-manager.yml` builds an unsigned IPA on GitHub Actions macOS. Sign the downloaded IPA with ESign/RBx9 Signer and your certificate before installing.

The app doesn't change source files until you authorize it and perform an action. Removing a catalog listing doesn't delete GitHub Release binary assets.


## IPA dylib injection (v1.2.0)

The ESign tab now includes a staged IPA editor:
1. Select an IPA from iPhone Files.
2. Optionally select multiple .dylib files from Files, remove duplicates, and review the selection.
3. Choose **Inject Dylibs & Publish** to upload the IPA as a draft-release input (not a .ipa catalog entry), then publish a release that triggers `inject-source-manager-ipa.yml`.
4. The workflow packages the selected dylibs into the app's Frameworks directory and modifies the main Mach-O executable's load commands, checks the output and uploads only the validated injected IPA asset.
5. Once verified, GitHub dispatches the existing `build-ipa-source.yml` to add the injected IPA to the ESign catalog.

The output is **unsigned** and must be signed using a compatible provisioning profile / signing certificate by each person installing it. The repository does not automatically sign apps for downloaders. Some IPAs are encrypted or have unusual bundle layouts and cannot be safely modified; in these cases the workflow fails without publishing a modified app. Use this feature only for apps you own or are authorized to redistribute and modify.
