import os
import shutil

from util import safe_mkdir


def divide_cuhk(cuhk_dir):
    safe_mkdir(os.path.join(cuhk_dir, 'probe'))
    safe_mkdir(os.path.join(cuhk_dir, 'test'))
    for i, image_name in enumerate(sorted(os.listdir(cuhk_dir))):
        if '.' not in image_name:
            continue
        if i % 2 == 0:
            shutil.copyfile(os.path.join(cuhk_dir, image_name), os.path.join(cuhk_dir, 'probe', image_name))
        else:
            shutil.copyfile(os.path.join(cuhk_dir, image_name), os.path.join(cuhk_dir, 'test', image_name))


if __name__ == '__main__':
    divide_cuhk('/home/wxt/ReidGAN/cuhk2market_style')