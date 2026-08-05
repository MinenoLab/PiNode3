#!/bin/bash

# ========================================
# IoT証明書をPiNodeに転送するスクリプト
# 初回セットアップ時に一度だけ実行する
#
# 使い方: ./scripts/transfer_certs.sh <device-name> <pinode-ip>
# 例:     ./scripts/transfer_certs.sh PiNode36 192.168.1.100
# ========================================

set -e

DEVICE_NAME=$1
PINODE_IP=$2
PINODE_USER=${3:-pinode3}   # デフォルトユーザー: pinode3
REGION="ap-northeast-1"
REMOTE_CERT_DIR="/etc/iot"

if [ -z "$DEVICE_NAME" ] || [ -z "$PINODE_IP" ]; then
    echo "エラー: デバイス名とIPアドレスを指定してください"
    echo "使い方: ./scripts/transfer_certs.sh <device-name> <pinode-ip>"
    echo "例:     ./scripts/transfer_certs.sh PiNode36 192.168.1.100"
    exit 1
fi

CERT_DIR="certs/${DEVICE_NAME}"

# ─────────────────────────────────────────
# 証明書ファイルの存在確認
# register_device.sh が先に実行されている必要がある
# ─────────────────────────────────────────
if [ ! -f "${CERT_DIR}/certificate.pem.crt" ]; then
    echo "エラー: 証明書が見つかりません: ${CERT_DIR}/certificate.pem.crt"
    echo "先に register_device.sh を実行してください:"
    echo "  ./scripts/register_device.sh ${DEVICE_NAME}"
    exit 1
fi

echo "=========================================="
echo "証明書転送開始"
echo "  デバイス: ${DEVICE_NAME}"
echo "  転送先: ${PINODE_USER}@${PINODE_IP}:${REMOTE_CERT_DIR}"
echo "=========================================="

# ─────────────────────────────────────────
# リモートでディレクトリを作成
# ─────────────────────────────────────────
echo "[1/3] リモートディレクトリを作成中..."
ssh -t "${PINODE_USER}@${PINODE_IP}" \
    "sudo mkdir -p ${REMOTE_CERT_DIR} && sudo chown ${PINODE_USER}:${PINODE_USER} ${REMOTE_CERT_DIR}"

# ─────────────────────────────────────────
# 証明書をPiNodeに転送
# ─────────────────────────────────────────
echo "[2/3] 証明書を転送中..."
scp "${CERT_DIR}/certificate.pem.crt" \
    "${PINODE_USER}@${PINODE_IP}:${REMOTE_CERT_DIR}/cert.pem"

scp "${CERT_DIR}/private.pem.key" \
    "${PINODE_USER}@${PINODE_IP}:${REMOTE_CERT_DIR}/private.key"

scp "${CERT_DIR}/AmazonRootCA1.pem" \
    "${PINODE_USER}@${PINODE_IP}:${REMOTE_CERT_DIR}/root-CA.pem"

# ─────────────────────────────────────────
# 秘密鍵のパーミッションを設定
# ─────────────────────────────────────────
echo "[3/3] パーミッションを設定中..."
ssh -t "${PINODE_USER}@${PINODE_IP}" \
    "chmod 600 ${REMOTE_CERT_DIR}/private.key"

echo ""
echo "=========================================="
echo "✅ 証明書の転送が完了しました"
echo "=========================================="
echo "転送したファイル:"
echo "  ${REMOTE_CERT_DIR}/cert.pem      ← デバイス証明書"
echo "  ${REMOTE_CERT_DIR}/private.key   ← 秘密鍵"
echo "  ${REMOTE_CERT_DIR}/root-CA.pem   ← Amazon ルートCA"
echo ""
echo "次のステップ:"
echo "  PiNode上で以下を実行してください:"
echo "  python3 /home/${PINODE_USER}/PiNode3/src/setup_certs.py"
echo "=========================================="