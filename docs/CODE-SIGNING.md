# Code signing – checklist

Goal: no more Gatekeeper and SmartScreen warnings, and updates that only install when they come from us.
Everything in the repository is prepared; it switches on as soon as the secrets below exist. Without them
the release is built exactly as before (Mac: own certificate «Verbalis Code Signing», Windows unsigned).

| | Mac | Windows |
|---|---|---|
| Who | Apple Developer Program, individual (Andrea) | SignPath Foundation (free for open source) |
| Cost | 99 USD per year | free |
| Publisher shown | «Andrea Frehner (TEAMID)» | «SignPath Foundation» |
| Per release | automatic (notarization takes a few minutes) | approve the signing request on signpath.io |
| Code | `tools/macos/sign_developer_id.sh`, `tools/macos/notarize.sh`, `packaging/macos/*.entitlements` | `packaging/signpath/artifact-configuration.xml` |
| Update check | `updates.check_same_signer` + `APPLE_TEAM_ID` | `updates.check_windows_signature` + `WINDOWS_PUBLISHER` |

## Mac – Developer ID and notarization

### 1. Enroll (Andrea)

1. Apple ID with two-factor authentication (the existing one is fine).
2. <https://developer.apple.com/programs/enroll/> → enroll as **individual** (no D-U-N-S number needed),
   pay 99 USD. Approval can take a day or two.
3. Note the **Team ID** (10 characters, developer.apple.com → Account → Membership details).

### 2. Bridge release (Claude, before any Developer ID build)

Installed Macs only accept updates signed like themselves (`updates.check_same_signer`). A build signed
with the Developer ID would be refused by every installed Verbalis. Therefore:

1. Put the Team ID into `src/verbalis/updates.py`: `APPLE_TEAM_ID = "XXXXXXXXXX"`.
2. Release that version **still signed with the own certificate** (do not add the Developer ID secrets yet).
   From this version on, an installed Verbalis accepts updates signed with the own certificate **or** by
   this Developer ID team – nothing else.
3. Wait until the Macs in use have updated to it (Andrea's, colleagues'). Anyone who skips it has to
   download the next version once by hand.

The workflow enforces the order: the Developer ID step fails if the certificate's team is not
`updates.APPLE_TEAM_ID` of the commit being built.

### 3. Certificate and API key (Andrea, on the Mac)

1. Xcode → Settings → Accounts → Manage Certificates → «+» → **Developer ID Application**
   (or developer.apple.com → Certificates → «+» → Developer ID Application, with a CSR from the
   Keychain Access app).
2. Keychain Access → «Meine Zertifikate» → «Developer ID Application: Andrea Frehner (TEAMID)» →
   export as `.p12` with a strong password. Keep the `.p12` and the password in Bitwarden.
3. App Store Connect → Users and Access → Integrations → **App Store Connect API** → Team Keys → «+»,
   name «Verbalis notarization», access **Developer**. Download `AuthKey_XXXX.p8` (only possible once –
   into Bitwarden), note the **Key ID** and the **Issuer ID**.

### 4. GitHub secrets (Andrea)

github.com/malaxy25/verbalis → Settings → Secrets and variables → Actions → New repository secret:

| Secret | Value |
|---|---|
| `MACOS_DEVID_CERT` | the `.p12` as Base64: `base64 -i DeveloperID.p12 \| pbcopy` |
| `MACOS_DEVID_PASSWORD` | the `.p12` password |
| `APPLE_API_KEY` | the whole content of `AuthKey_XXXX.p8` (including the BEGIN/END lines) |
| `APPLE_API_KEY_ID` | Key ID |
| `APPLE_API_ISSUER` | Issuer ID |

Keep `MACOS_SIGNING_CERT` / `MACOS_SIGNING_PASSWORD` for now (fallback); delete them once notarized
releases run.

### 5. First notarized release

The next release is signed with the Developer ID (hardened runtime, every binary on its own, timestamp),
self-tested, notarized, stapled and checked with `spctl`; the DMG is signed and notarized too. If
notarization fails, the log from Apple is printed in the «Notarize the app» step.

**After the switch macOS asks again for all three permissions**, because they are tied to the signature:
**Mikrofon**, **Systemaudio** (Bildschirm- & Systemaudioaufnahme, for the others' voices) and
**Bildschirmaufnahme** (snapshots). Tell users before the update; test it once yourself
(docs/TESTING.md, «Permissions after the certificate switch»).

### Entitlements (hardened runtime)

`packaging/macos/verbalis.entitlements` (Verbalis and verbalis-cli):

- `com.apple.security.device.audio-input` – microphone.
- `com.apple.security.cs.allow-unsigned-executable-memory` – libffi closures (soundcard's Core Audio
  callbacks via cffi, pywebview via PyObjC, ctypes).
- `com.apple.security.cs.disable-library-validation` – the optional Apple-GPU add-on (MLX) is unpacked to
  `~/.verbalis/mlx` at runtime and not signed by our team; library validation would block it.

`packaging/macos/audiotap.entitlements` (Swift helper): `com.apple.security.device.audio-input`.

System audio (Core Audio process tap) and screen capture need **no entitlement** outside the App Sandbox:
they are TCC permissions. The tap needs `NSAudioCaptureUsageDescription` in Info.plist (in
`packaging/verbalis.spec`); screen capture has no usage string. To be confirmed on the first notarized
build (manual test) – if the tap stays silent, check Console for TCC/«audio capture» denials.

## Windows – SignPath Foundation

### 1. Apply (Andrea)

1. Conditions (signpath.org/terms) – met: MIT license, no proprietary code, released, documented on the
   GitHub page, code signing policy in the README («Code signing policy» section, done), two-factor
   authentication on GitHub (required for SignPath and GitHub).
2. Apply at <https://signpath.org/apply> with the repository URL `https://github.com/malaxy25/verbalis`.
   Mention: Python app, Windows installer built by Inno Setup in GitHub Actions, one file per release.
3. After approval SignPath creates the organisation and project. In SignPath:
   - project slug **verbalis**, signing policy **release-signing** (otherwise set the variables below),
   - artifact configuration: paste `packaging/signpath/artifact-configuration.xml`,
   - trusted build system: GitHub.com (link the repository, install the SignPath GitHub app if asked),
   - create an API token for a user with submitter rights.

### 2. GitHub (Andrea)

| Kind | Name | Value |
|---|---|---|
| Secret | `SIGNPATH_API_TOKEN` | API token |
| Variable | `SIGNPATH_ORGANIZATION_ID` | organisation ID (SignPath → Organization settings) |
| Variable (optional) | `SIGNPATH_PROJECT_SLUG` | if not `verbalis` |
| Variable (optional) | `SIGNPATH_SIGNING_POLICY_SLUG` | if not `release-signing` |

### 3. Every release

The Windows job uploads the unsigned installer, submits it to SignPath and **waits up to 5 hours** for the
approval on signpath.io (e-mail from SignPath). Then it checks the signature and publishes the signed
installer. Manual test builds (Run workflow) are not signed.

### 4. Update check (Claude, after the first signed release)

When a signed release is out, set `WINDOWS_PUBLISHER = "SignPath Foundation"` in
`src/verbalis/updates.py` and release. From then on an installed Verbalis only runs an update installer
with a valid Authenticode signature of SignPath Foundation **and** the product name «Verbalis» (SignPath
signs many projects with the same certificate; the product name is enforced by the artifact
configuration). Setting it earlier would make apps refuse the still unsigned installers.

Only the installer is signed, not `Verbalis.exe` inside it – a second signing request (and approval) per
release would be needed for that. SmartScreen judges the downloaded installer.

## Order at a glance

1. Andrea: Apple enrollment, SignPath application (in parallel).
2. Claude: release with `APPLE_TEAM_ID` (bridge, still own certificate).
3. Andrea: Apple and SignPath secrets/variables in GitHub; Macs updated to the bridge release.
4. Next release: notarized Mac app, signed Windows installer. Andrea approves on signpath.io.
5. Claude: release with `WINDOWS_PUBLISHER`; later remove the old Mac secrets.
