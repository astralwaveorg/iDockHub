import hashlib
import plistlib
import re
import struct
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from xml.parsers.expat import ExpatError
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

MIB = 1024 * 1024
ARM64 = 0x0100000C
LC_CODE_SIGNATURE = 0x1D
CS_SUPERBLOB = 0xFADE0CC0
CS_ENTITLEMENTS = 0xFADE7171
CS_DER_ENTITLEMENTS = 0xFADE7172
INHERENT_ENTITLEMENTS = {"application-identifier", "com.apple.developer.team-identifier"}


def read_at(file, offset, size, end):
    if not 0 <= offset <= offset + size <= end:
        raise ValueError("Mach-O 中的偏移或长度无效")
    file.seek(offset)
    data = file.read(size)
    if len(data) != size:
        raise ValueError("Mach-O 文件不完整")
    return data


def unpack(fmt, data, offset=0):
    if offset < 0 or offset + struct.calcsize(fmt) > len(data):
        raise ValueError("Mach-O 签名或文件头不完整")
    return struct.unpack_from(fmt, data, offset)


def signature_entitlements(data):
    magic, length, count = unpack(">III", data)
    if magic != CS_SUPERBLOB or not 12 + 8 * count <= length <= len(data):
        raise ValueError("Mach-O 签名格式不受支持")
    entitlements = set()
    has_xml = has_der = False
    for i in range(count):
        slot, offset = unpack(">II", data, 12 + 8 * i)
        if slot not in (5, 7):
            continue
        kind, size = unpack(">II", data, offset)
        if not 12 + 8 * count <= offset or not 8 <= size <= length - offset:
            raise ValueError("Mach-O 权限块长度无效")
        if slot == 5 and kind == CS_ENTITLEMENTS:
            contents = data[offset + 8:offset + size]
            values = plistlib.loads(contents if contents.startswith(b"bplist00") else contents.rstrip(b"\x00"))
            if not isinstance(values, dict):
                raise ValueError("Mach-O 权限块不是字典")
            entitlements.update(values)
            has_xml = True
        elif slot == 7 and kind == CS_DER_ENTITLEMENTS:
            has_der = True
        else:
            raise ValueError("Mach-O 权限块格式不受支持")
    return entitlements, has_der and not has_xml


def slice_entitlements(file, start, size):
    end = start + size
    header = read_at(file, start, 32, end)
    if header[:4] != b"\xcf\xfa\xed\xfe" or unpack("<I", header, 4)[0] != ARM64:
        raise ValueError("IPA 的可执行文件不是 iOS arm64 Mach-O")
    count, length = unpack("<II", header, 16)
    if not 8 * count <= length <= MIB:
        raise ValueError("Mach-O 加载命令长度无效")
    commands = read_at(file, start + 32, length, end)
    offset = 0
    for _ in range(count):
        command, size = unpack("<II", commands, offset)
        if not 8 <= size <= length - offset:
            raise ValueError("Mach-O 加载命令不完整")
        if command == LC_CODE_SIGNATURE:
            if size < 16:
                raise ValueError("Mach-O 签名命令不完整")
            signature, length = unpack("<II", commands, offset + 8)
            if not length:
                return set(), False
            if length > 16 * MIB:
                raise ValueError("Mach-O 签名过大")
            return signature_entitlements(read_at(file, start + signature, length, end))
        offset += size
    return set(), False


def executable_entitlements(archive, path):
    info = archive.getinfo(path)
    with archive.open(info) as file:
        magic = read_at(file, 0, 4, info.file_size)
        if magic not in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
            return slice_entitlements(file, 0, info.file_size)

        # 通用二进制可能有多个 arm64 切片。软件源需要声明它们的权限。
        count = unpack(">I", read_at(file, 4, 4, info.file_size))[0]
        if not 1 <= count <= 64:
            raise ValueError("Mach-O 切片数量无效")
        fmt = ">IIQQII" if magic[-1] == 0xBF else ">IIIII"
        length = struct.calcsize(fmt)
        table = read_at(file, 8, count * length, info.file_size)
        slices = sorted(
            (offset, size)
            for cpu, _, offset, size, *_ in struct.iter_unpack(fmt, table)
            if cpu == ARM64
        )
        if not slices:
            raise ValueError("IPA 没有 iOS arm64 切片")
        entitlements, needs_override = set(), False
        for offset, size in slices:
            if not 8 + count * length <= offset < offset + size <= info.file_size:
                raise ValueError("Mach-O 切片范围无效")
            found, missing = slice_entitlements(file, offset, size)
            entitlements.update(found)
            needs_override |= missing
        return entitlements, needs_override


def read_plist(archive, path):
    info = archive.getinfo(path)
    if info.file_size > MIB:
        raise ValueError("IPA 中的 Info.plist 过大")
    plist = plistlib.loads(archive.read(info))
    if not isinstance(plist, dict):
        raise ValueError("IPA 中的 Info.plist 不是字典")
    return plist


def mobile_devices(app):
    supported = app.get("CFBundleSupportedPlatforms")
    platform = app.get("DTPlatformName", "")
    families = app.get("UIDeviceFamily", [])
    if (
        (supported and "iPhoneOS" not in supported)
        or (platform and platform != "iphoneos")
        or (families and not any(family in (1, 2) for family in families))
    ):
        raise ValueError("该 IPA 不适用于 iPhone 或 iPad。请用 assetPattern 选择 iOS 资产")
    return [device for family, device in ((1, "iPhone"), (2, "iPad")) if family in families]


def read_ipa(file):
    with ZipFile(file) as archive:
        names = archive.namelist()
        main = [path for path in names if re.fullmatch(r"Payload/[^/]+\.app/Info\.plist", path)]
        if len(main) != 1:
            raise ValueError("IPA 必须包含一个主应用 Info.plist")
        root = main[0].removesuffix("/Info.plist")
        app = read_plist(archive, main[0])
        version = {
            "bundleIdentifier": app.get("CFBundleIdentifier"),
            "version": app.get("CFBundleShortVersionString"),
            "buildVersion": app.get("CFBundleVersion"),
        }
        if not all(isinstance(value, str) and value.strip() for value in version.values()):
            raise ValueError("IPA 缺少 bundleIdentifier、版本号或构建号")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", version["bundleIdentifier"]):
            raise ValueError("IPA 的 bundleIdentifier 无效")
        version["name"] = next(
            (app[key].strip() for key in ("CFBundleDisplayName", "CFBundleName")
             if isinstance(app.get(key), str) and app[key].strip()), ""
        )
        if isinstance(app.get("MinimumOSVersion"), str) and app["MinimumOSVersion"]:
            version["minOSVersion"] = app["MinimumOSVersion"]
        version["devices"] = mobile_devices(app)

        entitlements, privacy, needs_override = set(), {}, False
        bundles = [main[0], *sorted(
            path for path in names
            if path.startswith(root + "/")
            and re.search(r"/(?:[^/]+\.appex|[^/]+\.app)/Info\.plist$", path)
            and path != main[0]
        )]
        for path in bundles:
            info = app if path == main[0] else read_plist(archive, path)
            for key, value in info.items():
                if re.fullmatch(r".+UsageDescription(?:[-~].*)?", key) and isinstance(value, str):
                    privacy.setdefault(re.split(r"[-~]", key, maxsplit=1)[0], value)
            executable = info.get("CFBundleExecutable")
            if not isinstance(executable, str) or not executable or "/" in executable or executable in (".", ".."):
                raise ValueError("IPA 缺少有效的 CFBundleExecutable")
            found, missing = executable_entitlements(archive, path.rsplit("/", 1)[0] + "/" + executable)
            entitlements.update(found)
            needs_override |= missing
        version["privacy"] = dict(sorted(privacy.items()))
        version["entitlements"] = sorted(entitlements - INHERENT_ENTITLEMENTS)
        version["needsEntitlementsOverride"] = needs_override
        return version


def inspect_asset(asset):
    url = urlsplit(asset["browser_download_url"])
    if url.scheme != "https" or url.netloc != "github.com" or "/releases/download/" not in url.path:
        raise ValueError("IPA 下载地址不是公开的 GitHub Release 资产")
    size = asset["size"]
    if type(size) is not int or not 0 < size <= 2**31 - 1:
        raise ValueError("IPA 大小超出软件源可用范围")
    checksum = hashlib.sha256()
    with tempfile.TemporaryFile() as file:
        with urlopen(Request(url.geturl(), headers={"User-Agent": "iDockHub"}), timeout=15) as response:
            while chunk := response.read(MIB):
                if file.tell() + len(chunk) > size:
                    raise ValueError("IPA 实际大小大于 GitHub 标注值")
                file.write(chunk)
                checksum.update(chunk)
        if file.tell() != size:
            raise ValueError("IPA 下载不完整")
        if asset.get("digest") and asset["digest"] != "sha256:" + checksum.hexdigest():
            raise ValueError("IPA 的 SHA-256 与 GitHub 记录不符")
        try:
            return read_ipa(file)
        except (BadZipFile, plistlib.InvalidFileException, ExpatError, ZlibError,
                EOFError, KeyError, RuntimeError, OverflowError) as exc:
            raise ValueError(f"无法读取 IPA：{exc}") from exc
