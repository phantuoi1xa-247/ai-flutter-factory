#!/usr/bin/env python3
"""Kiểm tra kiến trúc Clean Architecture + Bloc cho dự án Flutter.

In ra JSON: {"issues": [...], "warnings": [...], "features": [...]}
- issues: vi phạm bắt buộc phải sửa (chặn "đạt")
- warnings: góp ý, không chặn
"""
import json
import os
import re
import sys

ROOT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
LIB = os.path.join(ROOT, "lib")
TEST = os.path.join(ROOT, "test")
IMPORT_RE = re.compile(r"^\s*(?:import|export)\s+['\"]([^'\"]+)['\"]", re.M)
LAYER_RE = re.compile(r"/features/([^/]+)/(domain|data|presentation)/")

DOMAIN_FORBIDDEN = (
    "package:flutter/", "package:flutter_bloc", "package:bloc", "package:shared_preferences",
    "package:http", "package:dio", "package:hive", "package:sqflite", "package:get_it",
    "dart:ui", "dart:html", "dart:io",
)
DATA_SOURCE_PKGS = ("package:shared_preferences", "package:http", "package:dio", "package:sqflite", "package:hive")

issues, warnings, features = [], [], []


def dart_files(d):
    if not os.path.isdir(d):
        return
    for dp, _, fs in os.walk(d):
        for f in sorted(fs):
            if f.endswith(".dart"):
                yield os.path.join(dp, f)


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def read(p):
    with open(p, encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def layer_of(path):
    m = LAYER_RE.search("/" + path.replace("\\", "/"))
    return (m.group(1), m.group(2)) if m else (None, None)


def target_of(src_file, imp):
    if imp.startswith("package:app/"):
        return layer_of("lib/" + imp[len("package:app/"):])
    if imp.startswith(("package:", "dart:")):
        return (None, None)
    resolved = os.path.normpath(os.path.join(os.path.dirname(src_file), imp))
    return layer_of(rel(resolved))


if not os.path.isfile(os.path.join(LIB, "main.dart")):
    issues.append("Thiếu lib/main.dart")

feat_root = os.path.join(LIB, "features")
if not os.path.isdir(feat_root):
    issues.append("Thiếu lib/features/<tên_feature>/ – Clean Architecture phải chia theo feature")
else:
    for name in sorted(os.listdir(feat_root)):
        fd = os.path.join(feat_root, name)
        if not os.path.isdir(fd):
            continue
        features.append(name)
        for layer in ("domain", "data", "presentation"):
            if not os.path.isdir(os.path.join(fd, layer)):
                issues.append(f'Feature "{name}" thiếu lớp {layer}/')
        dom = os.path.join(fd, "domain")
        if os.path.isdir(dom):
            for sub in ("entities", "repositories", "usecases"):
                if not os.path.isdir(os.path.join(dom, sub)):
                    warnings.append(f'Feature "{name}": domain nên có thư mục {sub}/')
        pres = os.path.join(fd, "presentation")
        if os.path.isdir(pres):
            names = [os.path.basename(x) for x in dart_files(pres)]
            if not any(n.endswith(("_bloc.dart", "_cubit.dart")) for n in names):
                issues.append(f'Feature "{name}": presentation thiếu Bloc/Cubit (*_bloc.dart hoặc *_cubit.dart)')
    if not features:
        issues.append("lib/features/ chưa có feature nào")

all_lib = []
for f in dart_files(LIB):
    r = rel(f)
    src = read(f)
    all_lib.append(src)
    n_lines = src.count("\n") + 1
    if n_lines > 400:
        warnings.append(f"{r} dài {n_lines} dòng – nên tách nhỏ")
    feat, layer = layer_of(r)
    for imp in IMPORT_RE.findall(src):
        t_feat, t_layer = target_of(f, imp)
        if layer == "domain":
            if imp.startswith(DOMAIN_FORBIDDEN):
                issues.append(f"{r}: lớp domain không được import {imp}")
            if t_layer in ("data", "presentation"):
                issues.append(f"{r}: domain không được phụ thuộc lớp {t_layer} ({imp})")
        elif layer == "data":
            if t_layer == "presentation" or imp.startswith(("package:flutter/material", "package:flutter/widgets", "package:flutter_bloc")):
                issues.append(f"{r}: lớp data không được phụ thuộc UI ({imp})")
        elif layer == "presentation":
            if t_layer == "data":
                issues.append(f"{r}: presentation không được import trực tiếp lớp data ({imp}) – đi qua domain + get_it")
            if imp.startswith(DATA_SOURCE_PKGS):
                issues.append(f"{r}: presentation không được gọi trực tiếp nguồn dữ liệu ({imp})")
        if feat and t_feat and t_feat != feat and t_layer in ("data", "presentation"):
            warnings.append(f"{r}: phụ thuộc chéo sang feature khác ({imp})")
    if layer == "presentation" and "setState(" in src:
        warnings.append(f"{r}: dùng setState – state nghiệp vụ nên nằm trong Bloc/Cubit")

joined = "\n".join(all_lib)
if "GetIt" not in joined:
    issues.append("Chưa cấu hình dependency injection bằng get_it (GetIt)")

tests_src = "\n".join(read(f) for f in dart_files(TEST))
if "testWidgets(" not in tests_src:
    issues.append("Chưa có widget test (testWidgets)")
if "blocTest" not in tests_src:
    warnings.append("Chưa có bloc test (blocTest)")

print(json.dumps({"issues": issues, "warnings": warnings, "features": features}, ensure_ascii=False))
