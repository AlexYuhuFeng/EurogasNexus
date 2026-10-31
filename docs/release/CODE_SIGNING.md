# Code signing for Windows installers

Unsigned installers trigger Microsoft SmartScreen ("Windows protected your PC") and most
corporate endpoint policies block them. Signing is required before 1.0.0 (compliance
finding S1). The release workflow signs automatically once the certificate below exists.

## Which route

Since June 2023 the CA/Browser Forum requires publicly trusted code-signing keys to live in
certified hardware (FIPS 140-2 level 2 or higher). A certificate can no longer be bought as a
`.pfx` file and stored as a GitHub secret. There are three practical routes:

| Route | Cost (indicative) | Good for | Notes |
|---|---|---|---|
| **Azure Artifact Signing** (formerly Trusted Signing), **recommended** | about USD 10 a month (Basic, 5,000 signatures) | Products shipped to customers | Microsoft holds the key and issues short-lived certificates; the workflow signs with OIDC and stores no secret. Needs a paid Azure subscription (not free or trial). Organisations must pass identity validation, which can take a week or more |
| Commercial OV certificate with a cloud HSM (DigiCert KeyLocker, SSL.com eSigner, GlobalSign, Sectigo) | about USD 300-700 a year, plus HSM or cloud-signing fees | Entities Azure does not validate (for example a China-registered company, through a CA with a China presence) | Needs a signing step for that vendor's tool; ask and it is added beside the Azure one |
| The customer's internal enterprise CA | none | A dedicated network where IT deploys through Intune or GPO and trusts its own CA | Uses the existing `pfx` provider with the firm's certificate; not trusted outside that firm |

## What I need from you (Azure route)

Signing up requires a legal person and identity checks that only your company can complete.
Prepare:

1. **Legal entity**: the exact registered company name, registration number and country,
   registered address, and a public website on a domain the company controls.
2. **A verifiable public record** of the company (business registry entry; a D-U-N-S number
   helps). Microsoft checks the organisation against such records and may ask for documents
   such as a certificate of incorporation.
3. **A named contact** with a company e-mail address (on the company domain) and phone
   number, and a government ID for the person who completes the verification.
4. **An Azure subscription** on a paid (pay-as-you-go or enterprise) plan, and someone with
   rights to create resources and an Entra ID app registration in it.
5. **Eligibility**: Microsoft currently validates organisations in a limited set of
   countries (the US, Canada, the EU and the UK at the time of writing) and may require some
   years of verifiable trading history. Check the current list on Microsoft Learn ("Artifact
   Signing FAQ") before applying; if the entity is not eligible, use the commercial-CA route.

Steps (about an hour of work plus Microsoft's validation time):

1. In the Azure portal create an **Artifact Signing account** (choose a region; note its
   endpoint, for example `https://weu.codesigning.azure.net/`).
2. Under **Identity validation**, start a **Public** organisation validation with the details
   above, and wait for *Completed*.
3. Create a **certificate profile** of type *Public Trust* linked to that validation.
4. Create an **Entra ID app registration** with a **federated credential** for GitHub Actions
   (organisation `AlexYuhuFeng`, repository `EurogasNexus`, entity type *Tag*, or
   *Environment* if you protect releases with one). Grant it the role **Artifact Signing
   Certificate Profile Signer** on the signing account.
5. In GitHub, **Settings → Secrets and variables → Actions**:
   - secrets: `AZURE_SIGNING_CLIENT_ID`, `AZURE_SIGNING_TENANT_ID`,
     `AZURE_SIGNING_SUBSCRIPTION_ID`
   - variables: `WINDOWS_CODE_SIGNING_ENABLED=true`,
     `WINDOWS_SIGNING_PROVIDER=azure-artifact-signing`, `AZURE_SIGNING_ENDPOINT`,
     `AZURE_SIGNING_ACCOUNT`, `AZURE_SIGNING_CERTIFICATE_PROFILE`

The next release run signs the `.exe` and `.msi` with SHA-256 and an RFC 3161 timestamp,
verifies each signature on the Windows runner, and records `authenticode_verified` in
`signing-state.json`. If anything is missing, the run records `unsigned_pending_external`
and stable promotion stays blocked; nothing is signed with a stand-in certificate.

## Linux

`.deb` packages get a detached GPG signature when `GPG_SIGNING_ENABLED=true` and
`GPG_SIGNING_KEY_ID` are set; otherwise checksums and build provenance attestations cover
them.
