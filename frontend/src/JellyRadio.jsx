import React, { useState, useRef, useEffect } from 'react';

const JellyRadio = ({
  items,
  defaultValue,
  onChange,
  chipColor = '#27272a',
  activeColor = '#f5f5f5',
  textColor = '#f5f5f5',
  activeTextColor = '#18181b',
  size = 'md',
  gap = 8,
  radius = 18,
}) => {
  const [activeIdx, setActiveIdx] = useState(() => {
    return items.findIndex(item => (typeof item === 'string' ? item : item.value) === defaultValue) || 0;
  });
  
  const [sliderStyle, setSliderStyle] = useState({});
  const containerRef = useRef(null);
  const itemRefs = useRef([]);

  useEffect(() => {
    if (itemRefs.current[activeIdx] && containerRef.current) {
      const activeElement = itemRefs.current[activeIdx];
      const containerRect = containerRef.current.getBoundingClientRect();
      const itemRect = activeElement.getBoundingClientRect();
      
      setSliderStyle({
        width: `${itemRect.width}px`,
        transform: `translateX(${itemRect.left - containerRect.left}px)`,
      });
    }
  }, [activeIdx, items]);

  const handleSelect = (index) => {
    const item = items[index];
    if (typeof item === 'object' && item.disabled) return;
    
    setActiveIdx(index);
    if (onChange) {
      const value = typeof item === 'string' ? item : item.value;
      onChange(value, index);
    }
  };

  const getPadding = () => {
    switch (size) {
      case 'sm': return '4px 10px';
      case 'lg': return '10px 24px';
      case 'md':
      default: return '6px 16px';
    }
  };

  const getFontSize = () => {
    switch (size) {
      case 'sm': return '0.75rem';
      case 'lg': return '1rem';
      case 'md':
      default: return '0.875rem';
    }
  };

  return (
    <div 
      ref={containerRef}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: `${gap}px`,
        position: 'relative',
        background: chipColor,
        padding: '4px',
        borderRadius: `${radius + 4}px`,
        border: '1px solid rgba(255,255,255,0.05)',
      }}
    >
      {/* The animated "Jelly" Slider background */}
      <div 
        style={{
          position: 'absolute',
          top: '4px',
          bottom: '4px',
          left: 0,
          backgroundColor: activeColor,
          borderRadius: `${radius}px`,
          transition: 'all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)',
          ...sliderStyle
        }}
      />

      {items.map((item, i) => {
        const isString = typeof item === 'string';
        const label = isString ? item : item.label;
        const icon = isString ? null : item.icon;
        const disabled = isString ? false : item.disabled;
        const isActive = activeIdx === i;

        return (
          <button
            key={isString ? item : item.value}
            ref={el => itemRefs.current[i] = el}
            onClick={() => handleSelect(i)}
            disabled={disabled}
            style={{
              position: 'relative',
              zIndex: 1,
              background: 'transparent',
              border: 'none',
              padding: getPadding(),
              fontSize: getFontSize(),
              fontWeight: 600,
              color: isActive ? activeTextColor : textColor,
              cursor: disabled ? 'not-allowed' : 'pointer',
              opacity: disabled ? 0.4 : 1,
              borderRadius: `${radius}px`,
              transition: 'color 0.3s ease',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontFamily: 'inherit',
            }}
          >
            {icon && <span style={{ display: 'flex', alignItems: 'center' }}>{icon}</span>}
            {label}
          </button>
        );
      })}
    </div>
  );
};

export default JellyRadio;
