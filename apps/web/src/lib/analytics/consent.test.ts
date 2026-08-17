import { beforeEach, describe, expect, it } from "vitest";
import {
  CONSENT_COOKIE,
  CONSENT_DENIED,
  CONSENT_GRANTED,
  CONSENT_MAX_AGE,
  clearAnalyticsCookies,
  consentCookieString,
  deletionCookieStrings,
  readConsent,
  writeConsent,
} from "./consent";

function clearAllCookies() {
  for (const part of document.cookie.split(";")) {
    const name = part.split("=")[0]?.trim();
    if (name) document.cookie = `${name}=; Path=/; Max-Age=0`;
  }
}

beforeEach(clearAllCookies);

describe("consent cookie", () => {
  it("reads granted/denied and treats anything else as unknown (re-ask)", () => {
    expect(readConsent()).toBe("unknown");

    document.cookie = `${CONSENT_COOKIE}=${CONSENT_GRANTED}; Path=/`;
    expect(readConsent()).toBe("granted");

    document.cookie = `${CONSENT_COOKIE}=${CONSENT_DENIED}; Path=/`;
    expect(readConsent()).toBe("denied");

    // 版本不符（未來 v2）→ 當作沒回答過，重新詢問，不繼承舊同意。
    document.cookie = `${CONSENT_COOKIE}=granted_v2; Path=/`;
    expect(readConsent()).toBe("unknown");
  });

  it("round-trips on a host-only origin (localhost 退化，無 Domain/Secure)", () => {
    writeConsent("granted");
    expect(readConsent()).toBe("granted");
    writeConsent("denied");
    expect(readConsent()).toBe("denied");
  });

  it("writes the exact cross-subdomain contract on ntutbox.com hosts", () => {
    const s = consentCookieString("granted", "course.ntutbox.com", "https:");
    expect(s).toBe(
      `${CONSENT_COOKIE}=${CONSENT_GRANTED}; Domain=.ntutbox.com; Path=/; Max-Age=${CONSENT_MAX_AGE}; SameSite=Lax; Secure`,
    );
    expect(consentCookieString("denied", "ntutbox.com", "https:")).toContain(`=${CONSENT_DENIED}`);
    expect(CONSENT_MAX_AGE).toBe(15552000);
  });

  it("degrades to host-only (no Domain, no Secure) off ntutbox.com", () => {
    const s = consentCookieString("granted", "localhost", "http:");
    expect(s).not.toContain("Domain=");
    expect(s).not.toContain("Secure");
    expect(s).toContain("SameSite=Lax");
  });

  it("deletes both host-only and .ntutbox.com variants of a cookie", () => {
    expect(deletionCookieStrings("_ga", "course.ntutbox.com")).toEqual([
      "_ga=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0",
      "_ga=; Domain=.ntutbox.com; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0",
    ]);
    expect(deletionCookieStrings("_ga", "localhost")).toHaveLength(1);
  });

  it("revoke clears _ga / _ga_* / _gcl_* and the consent cookie, keeping unrelated ones", () => {
    document.cookie = `${CONSENT_COOKIE}=${CONSENT_GRANTED}; Path=/`;
    document.cookie = "_ga=GA1.1.123.456; Path=/";
    document.cookie = "_ga_ABC123=GS1.1.789; Path=/";
    document.cookie = "_gcl_au=1.1.222.333; Path=/";
    document.cookie = "ntutbox-draft-115-1=keepme; Path=/";

    clearAnalyticsCookies();

    expect(document.cookie).not.toContain("_ga");
    expect(document.cookie).not.toContain("_gcl_au");
    expect(document.cookie).not.toContain(CONSENT_COOKIE);
    // 產品自己的狀態不能被分析撤回波及。
    expect(document.cookie).toContain("ntutbox-draft-115-1=keepme");
  });
});
