import React, { useState, useEffect } from 'react';
import { Modal, Image } from 'antd';
import './index.css';

export interface ImagePreviewProps {
  visible: boolean;
  src: string;
  alt?: string;
  title?: string;
  onClose: () => void;
}

const ImagePreview: React.FC<ImagePreviewProps> = ({
  visible,
  src,
  alt = '预览图片',
  title,
  onClose,
}) => {
  const [imgError, setImgError] = useState(false);

  useEffect(() => {
    if (visible) {
      setImgError(false);
    }
  }, [visible, src]);

  const isError = src === 'error' || imgError;
  const isLoading = !src && !isError;

  return (
    <Modal
      open={visible}
      onCancel={onClose}
      footer={null}
      centered
      width="90%"
      style={{ maxWidth: '1200px' }}
      className="image-preview-modal"
      closeIcon={
        <div className="preview-close-btn">
          <span>✕</span>
        </div>
      }
    >
      <div className="preview-container">
        {title && <div className="preview-title">{title}</div>}
        <div className="preview-image-wrapper">
          {isError ? (
            <div className="preview-error">
              <div className="error-icon">⚠</div>
              <div className="error-text">无法加载预览图片</div>
            </div>
          ) : isLoading ? (
            <div className="preview-loading">
              <div className="loading-spinner" />
              <div className="loading-text">加载中...</div>
            </div>
          ) : (
            <Image
              src={src}
              alt={alt}
              className="preview-image"
              preview={false}
              onError={() => setImgError(true)}
            />
          )}
        </div>
      </div>
    </Modal>
  );
};

export default ImagePreview;
