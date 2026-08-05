#!/bin/bash

# ========================================
# IoTデバイス登録スクリプト
# 使い方: ./scripts/register_device.sh <device-name>
# 例:     ./scripts/register_device.sh PiNode3_21
#
# 前提: jq がインストールされていること
#   Mac:   brew install jq
#   Linux: sudo apt install jq
# ========================================

set -e

DEVICE_NAME=$1
REGION="ap-northeast-1"
POLICY_NAME="AgriDevicePolicy"

# ─────────────────────────────────────────
# 引数チェック
# ─────────────────────────────────────────
if [ -z "$DEVICE_NAME" ]; then
    echo "エラー: デバイス名を指定してください"
    echo "使い方: ./scripts/register_device.sh <device-name>"
    echo "例:     ./scripts/register_device.sh PiNode3_21"
    exit 1
fi

# jq がインストールされているか確認
if ! command -v jq &> /dev/null; then
    echo "エラー: jq がインストールされていません"
    echo "  Mac:   brew install jq"
    echo "  Linux: sudo apt install jq"
    exit 1
fi

CERT_DIR="certs/${DEVICE_NAME}"

# ─────────────────────────────────────────
# 既存デバイスチェック
# 同名の Thing が既に AWS 上に存在する場合は中断する
# → 証明書の二重発行を防ぐ
# ─────────────────────────────────────────
echo "既存デバイスを確認中..."
EXISTING_THING=$(aws iot describe-thing \
    --thing-name "$DEVICE_NAME" \
    --region "$REGION" \
    --query 'thingName' \
    --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_THING" ]; then
    echo ""
    echo "エラー: デバイス '$DEVICE_NAME' は既に登録されています"
    echo ""
    echo "対処方法:"
    echo "  削除して再登録 : ./scripts/unregister_device.sh $DEVICE_NAME"
    echo "  一覧確認       : ./scripts/device_list.sh"
    echo ""
    echo "※ 既存の証明書をそのまま使う場合は再登録不要です"
    echo "  Secrets Manager から取得:"
    echo "  aws secretsmanager get-secret-value --secret-id iot-cert/$DEVICE_NAME --region $REGION"
    exit 1
fi

# ─────────────────────────────────────────
# エラー時のクリーンアップ関数
# set -e でスクリプトが途中終了した場合に呼ばれる
# ─────────────────────────────────────────
cleanup_on_error() {
    echo ""
    echo "⚠️  エラーが発生しました。クリーンアップを実行します..."

    # 証明書ARNが取得済みの場合のみ削除処理を行う
    if [ -n "$CERT_ARN" ] && [ -n "$CERT_ID" ]; then
        echo "  証明書をデタッチ・削除中..."
        aws iot detach-policy \
            --policy-name "$POLICY_NAME" \
            --target "$CERT_ARN" \
            --region "$REGION" 2>/dev/null || true

        aws iot detach-thing-principal \
            --thing-name "$DEVICE_NAME" \
            --principal "$CERT_ARN" \
            --region "$REGION" 2>/dev/null || true

        aws iot update-certificate \
            --certificate-id "$CERT_ID" \
            --new-status INACTIVE \
            --region "$REGION" 2>/dev/null || true

        aws iot delete-certificate \
            --certificate-id "$CERT_ID" \
            --force-delete \
            --region "$REGION" 2>/dev/null || true
    fi

    # ローカルの証明書ファイルを削除
    rm -rf "$CERT_DIR"

    echo "クリーンアップ完了。再度スクリプトを実行してください。"
}

# エラー発生時に cleanup_on_error を呼ぶ
trap cleanup_on_error ERR

echo "=========================================="
echo "デバイス登録開始: $DEVICE_NAME"
echo "=========================================="

mkdir -p "$CERT_DIR"

# ─────────────────────────────────────────
# 1. Thing を作成
# ─────────────────────────────────────────
echo "[1/6] Thing を作成中..."
aws iot create-thing \
    --thing-name "$DEVICE_NAME" \
    --region "$REGION" \
    > /dev/null

# ─────────────────────────────────────────
# 2. 証明書とキーペアを作成
# ─────────────────────────────────────────
echo "[2/6] 証明書を発行中..."
CERT_OUTPUT=$(aws iot create-keys-and-certificate \
    --set-as-active \
    --certificate-pem-outfile "${CERT_DIR}/certificate.pem.crt" \
    --public-key-outfile "${CERT_DIR}/public.pem.key" \
    --private-key-outfile "${CERT_DIR}/private.pem.key" \
    --region "$REGION" \
    --output json)

# jq で安全にARNとIDを取り出す
CERT_ARN=$(echo "$CERT_OUTPUT" | jq -r '.certificateArn')
CERT_ID=$(echo "$CERT_OUTPUT"  | jq -r '.certificateId')

echo "  証明書ARN: $CERT_ARN"

# 後でunregisterスクリプトが使えるようにファイルにも保存
echo "$CERT_ARN" > "${CERT_DIR}/certificate-arn.txt"
echo "$CERT_ID"  > "${CERT_DIR}/certificate-id.txt"

# ─────────────────────────────────────────
# 3. Amazon Root CA をダウンロード
# ─────────────────────────────────────────
echo "[3/6] Amazon Root CA をダウンロード中..."
if [ ! -f "${CERT_DIR}/AmazonRootCA1.pem" ]; then
    curl -sf -o "${CERT_DIR}/AmazonRootCA1.pem" \
        https://www.amazontrust.com/repository/AmazonRootCA1.pem
    echo "  ダウンロード完了"
else
    echo "  既にあるためスキップ"
fi

# ─────────────────────────────────────────
# 4. ポリシーを証明書にアタッチ
# ─────────────────────────────────────────
echo "[4/6] ポリシーをアタッチ中..."
aws iot attach-policy \
    --policy-name "$POLICY_NAME" \
    --target "$CERT_ARN" \
    --region "$REGION"

# ─────────────────────────────────────────
# 5. 証明書を Thing にアタッチ
# ─────────────────────────────────────────
echo "[5/6] 証明書を Thing にアタッチ中..."
aws iot attach-thing-principal \
    --thing-name "$DEVICE_NAME" \
    --principal "$CERT_ARN" \
    --region "$REGION"

# ─────────────────────────────────────────
# 6. Secrets Manager に保存
#    ※ jq で改行を \n に変換して JSON を安全に構築する
#      シェル変数を直接 JSON に埋め込むと改行が壊れるため必須
# ─────────────────────────────────────────
echo "[6/6] Secrets Manager に保存中..."
SECRET_NAME="iot-cert/${DEVICE_NAME}"

# jq の --rawfile でファイルを読み込み、改行を含む内容を安全にJSON化する
SECRET_JSON=$(jq -n \
    --rawfile certificatePem "${CERT_DIR}/certificate.pem.crt" \
    --rawfile privateKey     "${CERT_DIR}/private.pem.key" \
    --arg certificateArn    "$CERT_ARN" \
    --arg certificateId     "$CERT_ID" \
    --arg thingName         "$DEVICE_NAME" \
    '{
        certificatePem: $certificatePem,
        privateKey:     $privateKey,
        certificateArn: $certificateArn,
        certificateId:  $certificateId,
        thingName:      $thingName
    }')

# Secret が既に存在する場合は update、なければ create
if aws secretsmanager describe-secret \
        --secret-id "$SECRET_NAME" \
        --region "$REGION" > /dev/null 2>&1; then
    echo "  既存の Secret を更新します"
    aws secretsmanager update-secret \
        --secret-id "$SECRET_NAME" \
        --secret-string "$SECRET_JSON" \
        --region "$REGION" > /dev/null
else
    aws secretsmanager create-secret \
        --name "$SECRET_NAME" \
        --description "IoT certificate for ${DEVICE_NAME}" \
        --secret-string "$SECRET_JSON" \
        --region "$REGION" > /dev/null
fi

# ─────────────────────────────────────────
# 完了
# ─────────────────────────────────────────
# 正常終了したので trap を解除
trap - ERR

echo ""
echo "=========================================="
echo "✅ デバイス登録完了: $DEVICE_NAME"
echo "=========================================="
echo "証明書ファイル（デバイスに転送してください）:"
echo "  ${CERT_DIR}/certificate.pem.crt  ← デバイス証明書"
echo "  ${CERT_DIR}/private.pem.key      ← 秘密鍵"
echo "  ${CERT_DIR}/AmazonRootCA1.pem    ← ルートCA"
echo ""
echo "Secrets Manager から取得:"
echo "  aws secretsmanager get-secret-value --secret-id $SECRET_NAME --region $REGION"
echo ""
echo "デバイスの MQTT 設定:"
echo "  エンドポイント : (cdk deploy の IotEndpoint 出力を確認)"
echo "  トピック       : agri/sensors/${DEVICE_NAME}/data"
echo "  クライアントID : ${DEVICE_NAME}"
echo "=========================================="