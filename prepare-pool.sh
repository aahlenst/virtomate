#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <image-home>"
    exit 1
fi

image_home="$1"
pool_name="default"

# Import volumes
find "$image_home" -maxdepth 2 -mindepth 2 -type f -print0 | while read -d $'\0' file
do
  size=$(stat -Lc%s "$file")
  file_name=$(basename "$file")
  vol_format=$(qemu-img info --output json "$file" | jq -r .format)

  if [ "$file_name" = "efivars.fd" ] ; then
    # Prepend `efivars.fd` with the image name and use that as volume name. For example,
    # `/path/to/myimage/efivars.fd` would become `myimage-efivars.fd`.
    vol_name="$(basename "$(dirname "$file")")-efivars.fd"
  else
    # Use the file name as volume name
    vol_name=$(basename "$file")
  fi

  virsh vol-create-as --pool "$pool_name" "$vol_name" "$size" --format "$vol_format"
  virsh vol-upload --pool "$pool_name" "$vol_name" "$file" --sparse
done
