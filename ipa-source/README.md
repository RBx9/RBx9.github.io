# RBx9 IPA Library — Feather + ESign

Your public IPA library is **https://rbx9.github.io/ipa-source/**.

- Feather source: `https://rbx9.github.io/ipa/`
- ESign source: `https://rbx9.github.io/ipa/` (same URL as Feather)
- Existing Sileo tweak source (unchanged): `https://rbx9.github.io/`

## Upload your first IPA

1. Open [Create a GitHub Release](https://github.com/RBx9/RBx9.github.io/releases/new).
2. Create a **unique tag** for each version, e.g. `ipa-myapp-1.0`. The `ipa-` prefix is recommended but not required.
3. Attach one or more `.ipa` files to the release. Use filenames ending in lowercase `.ipa`.
4. Enter release notes if desired. These show as the version's What's New text.
5. Select **Publish release**.
6. Check [Publish Feather and ESign IPA Sources](https://github.com/RBx9/RBx9.github.io/actions/workflows/build-ipa-source.yml). Once the workflow succeeds and Pages updates, users refresh the source in Feather or ESign to see the apps.

Both apps can use the same universal feed. The older `/esign/`, `ipa-source/source.json`, and `ipa-source/esign.json` links remain available.

The workflow downloads the uploaded IPA, reads `Payload/*.app/Info.plist` for its bundle ID/name/version/build/minimum OS version, and publishes two JSON catalogs pointing to the GitHub Release asset. No need to manually edit source JSON for each upload.

To re-import an already published release, open Actions → Publish Feather and ESign IPA Sources → Run workflow → enter the release tag.

## Automatic Stremio iOS/iPadOS updates

Stremio (`com.stremio.pal`) is tracked from the
[gorlev/stremio-altstore iOS source](https://github.com/gorlev/stremio-altstore/blob/main/stremio-ios.json).
The workflow checks every **6 hours** (subject to GitHub Actions scheduling), selects only the
newest valid **iOS/iPadOS** version and build, and links directly to the IPA on
`dl.strem.io`. **No older Stremio versions or tvOS builds are added to this library.**
Updates appear at `https://rbx9.github.io/ipa/` after the GitHub Pages deployment.
If upstream is unavailable, the last published entry is retained rather than
replacing it with unverified information.

This is an unofficial feed integration; the apps and builds remain Stremio's,
and upstream metadata depends on that community-maintained mirror.

## Customize an app after uploading

Edit [catalog.json](https://github.com/RBx9/RBx9.github.io/blob/main/ipa-source/catalog.json) in GitHub. Apps are keyed by their bundle identifier. Edit `name`, `developerName`, `subtitle`, `localizedDescription`, `iconURL`, `category`, and optionally `screenshots` and `tintColor`. Committing an edit automatically regenerates both feeds. **Do not edit `source.json` or `esign.json` directly**, since the action overwrites them.

Icons should be publicly accessible via HTTPS. Newly uploaded apps use the repository icon until customized.

## Troubleshooting

- App missing: check the workflow logs and ensure the release contains a real `.ipa` asset.
- Import errors: verify the `source.json` or `esign.json` link returns JSON, and then refresh Sources.
- Signing errors: IPA distribution is separate from signing. Users need their own compatible certificates or signing methods.
- Only distribute apps you created or have permission to share.

This project is independent of Feather, ESign, Apple, Sileo, and AltStore.
