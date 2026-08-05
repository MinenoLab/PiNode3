#!/bin/bash

# ========================================
# IoTデバイス削除スクリプト
# 使い方: ./scripts/unregister_device.sh <device-name>
# 例:     ./scripts/unregister_device.sh PiNode3_21
# ========================================

set -e

DEVICE_NAME=$1
REGION="ap-northeast-1"
POLICY_NAME="AgriDevicePolicy"

if [ -z "$DEVICE_NAME" ]; then
    echo "エラー: デバイス名を指定してください"
    echo "使い方: ./scripts/unregister_device.sh <device-name>"
    exit 1
fi

CERT_DIR="certs/${DEVICE_NAME}"

echo "=========================================="
echo "デバイス削除開始: $DEVICE_NAME"
echo "=========================================="

# ─────────────────────────────────────────
# certificate-arn.txt が存在するかチェック
# ない場合は AWS から直接取得を試みる
# ─────────────────────────────────────────
if [ -f "${CERT_DIR}/certificate-arn.txt" ]; then
    CERT_ARN=$(cat "${CERT_DIR}/certificate-arn.txt")
    CERT_ID=$(cat "${CERT_DIR}/certificate-id.txt")
    echo "  証明書ARN: $CERT_ARN"
else
    echo "  certificate-arn.txt が見つかりません。AWS から取得を試みます..."
    # Thing にアタッチされている証明書を AWS から取得
    CERT_ARN=$(aws iot list-thing-principals \
        --thing-name "$DEVICE_NAME" \
        --region "$REGION" \
        --query 'principals[0]' \
        --output text 2>/dev/null || echo "")

    if [ -z "$CERT_ARN" ] || [ "$CERT_ARN" = "None" ]; then
        echo "  証明書が見つかりませんでした。Thing のみ削除します。"
        CERT_ARN=""
        CERT_ID=""
    else
        # ARN から証明書IDを取り出す（ARN の最後のセグメント）
        CERT_ID=$(basename "$CERT_ARN")
        echo "  証明書ARN: $CERT_ARN"
    fi
fi

# ─────────────────────────────────────────
# 証明書が存在する場合のクリーンアップ
# 削除の順序が重要：デタッチ → 無効化 → 削除
# ─────────────────────────────────────────
if [ -n "$CERT_ARN" ]; then
    echo "[1/5] ポリシーを証明書からデタッチ中..."
    aws iot detach-policy \
        --policy-name "$POLICY_NAME" \
        --target "$CERT_ARN" \
        --region "$REGION" 2>/dev/null || echo "  スキップ（既にデタッチ済み）"

    echo "[2/5] 証明書を Thing からデタッチ中..."
    aws iot detach-thing-principal \
        --thing-name "$DEVICE_NAME" \
        --principal "$CERT_ARN" \
        --region "$REGION" 2>/dev/null || echo "  スキップ（既にデタッチ済み）"

    echo "[3/5] 証明書を無効化中..."
    aws iot update-certificate \
        --certificate-id "$CERT_ID" \
        --new-status INACTIVE \
        --region "$REGION" 2>/dev/null || echo "  スキップ（既に無効）"

    echo "[4/5] 証明書を削除中..."
    aws iot delete-certificate \
        --certificate-id "$CERT_ID" \
        --force-delete \
        --region "$REGION" 2>/dev/null || echo "  スキップ（既に削除済み）"
else
    echo "[1-4/5] 証明書なし → スキップ"
fi

echo "[5/5] Thing を削除中..."
aws iot delete-thing \
    --thing-name "$DEVICE_NAME" \
    --region "$REGION" 2>/dev/null || echo "  スキップ（既に削除済み）"

# ─────────────────────────────────────────
# Secrets Manager から Secret を削除
# ─────────────────────────────────────────
SECRET_NAME="iot-cert/${DEVICE_NAME}"
echo "Secrets Manager から削除中..."
aws secretsmanager delete-secret \
    --secret-id "$SECRET_NAME" \
    --force-delete-without-recovery \
    --region "$REGION" \
    > /dev/null 2>&1 && echo "  削除完了" || echo "  スキップ（既に削除済み）"

# ─────────────────────────────────────────
# ローカルファイルを削除
# ※ AWS 側の削除が全部完了してから最後に消す
#   途中でエラーになっても certificate-arn.txt が残るので再実行できる
# ─────────────────────────────────────────
if [ -d "$CERT_DIR" ]; then
    rm -rf "$CERT_DIR"
    echo "ローカル証明書ファイルを削除しました: $CERT_DIR"
fi

echo ""
echo "=========================================="
echo "✅ デバイス削除完了: $DEVICE_NAME"
echo "=========================================="