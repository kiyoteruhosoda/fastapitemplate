/**
 * Browser-side handling of passkeys (WebAuthn).
 *
 * The server returns options as JSON with base64url strings and accepts responses in the same
 * format (py_webauthn compatible). This only does that conversion and the
 * `navigator.credentials` calls. No external libraries.
 */

export interface PasskeyChallenge {
  challenge_id: string
  public_key: Record<string, unknown>
}

/** Thrown when the user cancels the operation, so the error display can differ. */
export const PASSKEY_CANCELLED = 'passkey_cancelled'

export function isPasskeySupported(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.PublicKeyCredential !== 'undefined' &&
    !!navigator.credentials
  )
}

function base64urlToBuffer(value: string): ArrayBuffer {
  const base64 = value.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
  const binary = atob(padded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i)
  return bytes.buffer
}

function bufferToBase64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Convert a base64url credential list into WebAuthn descriptors. */
function toDescriptors(source: unknown): PublicKeyCredentialDescriptor[] {
  if (!Array.isArray(source)) return []
  return source.map((item) => {
    const descriptor = item as { id: string; type: 'public-key'; transports?: string[] }
    return {
      ...descriptor,
      id: base64urlToBuffer(descriptor.id),
    } as PublicKeyCredentialDescriptor
  })
}

/** Convert only the fields of the server's JSON that need an ArrayBuffer. */
function toCreationOptions(source: Record<string, unknown>): PublicKeyCredentialCreationOptions {
  const user = source.user as { id: string; name: string; displayName: string }
  return {
    ...source,
    challenge: base64urlToBuffer(source.challenge as string),
    user: { ...user, id: base64urlToBuffer(user.id) },
    excludeCredentials: toDescriptors(source.excludeCredentials),
  } as PublicKeyCredentialCreationOptions
}

function toRequestOptions(source: Record<string, unknown>): PublicKeyCredentialRequestOptions {
  return {
    ...source,
    challenge: base64urlToBuffer(source.challenge as string),
    allowCredentials: toDescriptors(source.allowCredentials),
  }
}

function assertCredential(credential: Credential | null): PublicKeyCredential {
  if (!credential) throw new Error(PASSKEY_CANCELLED)
  return credential as PublicKeyCredential
}

/** Have the authenticator create a new passkey and shape it for sending to the server. */
export async function createPasskey(
  publicKey: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const credential = assertCredential(
    await navigator.credentials.create({ publicKey: toCreationOptions(publicKey) }),
  )
  const response = credential.response as AuthenticatorAttestationResponse
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      attestationObject: bufferToBase64url(response.attestationObject),
      transports: typeof response.getTransports === 'function' ? response.getTransports() : [],
    },
  }
}

/** Have it sign with a registered passkey and shape it for sending to the server. */
export async function assertPasskey(
  publicKey: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const credential = assertCredential(
    await navigator.credentials.get({ publicKey: toRequestOptions(publicKey) }),
  )
  const response = credential.response as AuthenticatorAssertionResponse
  return {
    id: credential.id,
    rawId: bufferToBase64url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment ?? undefined,
    clientExtensionResults: credential.getClientExtensionResults(),
    response: {
      clientDataJSON: bufferToBase64url(response.clientDataJSON),
      authenticatorData: bufferToBase64url(response.authenticatorData),
      signature: bufferToBase64url(response.signature),
      userHandle: response.userHandle ? bufferToBase64url(response.userHandle) : null,
    },
  }
}

/** Detect the browser's cancellation (NotAllowedError). */
export function isPasskeyCancellation(error: unknown): boolean {
  if (error instanceof Error && error.message === PASSKEY_CANCELLED) return true
  return error instanceof DOMException && error.name === 'NotAllowedError'
}
